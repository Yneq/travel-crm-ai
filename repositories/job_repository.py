import json
from datetime import datetime, timedelta


PROVIDER = "voyageops-worker"
RUNNABLE_STATUSES = ("scheduled", "retrying")


def _decode(row: dict | None) -> dict | None:
    if row is not None and isinstance(row.get("payload"), str):
        row["payload"] = json.loads(row["payload"])
    return row


def get_job(connection, job_id: int, cursor=None) -> dict | None:
    owns_cursor = cursor is None
    cursor = cursor or connection.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT * FROM integration_events WHERE id = %s AND provider = %s",
            (job_id, PROVIDER),
        )
        return _decode(cursor.fetchone())
    finally:
        if owns_cursor:
            cursor.close()


def create_job(
    connection, event_type: str, idempotency_key: str, payload: dict, run_at: datetime
) -> tuple[dict, bool]:
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT * FROM integration_events WHERE idempotency_key = %s",
            (idempotency_key,),
        )
        existing = _decode(cursor.fetchone())
        if existing is not None:
            connection.commit()
            return existing, False
        cursor.execute(
            """
            INSERT IGNORE INTO integration_events(
                provider, event_type, idempotency_key, status, payload, next_attempt_at
            ) VALUES (%s, %s, %s, 'scheduled', %s, %s)
            """,
            (PROVIDER, event_type, idempotency_key, json.dumps(payload), run_at),
        )
        created = cursor.rowcount == 1
        cursor.execute(
            "SELECT * FROM integration_events WHERE idempotency_key = %s",
            (idempotency_key,),
        )
        job = _decode(cursor.fetchone())
        connection.commit()
        return job, created
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def list_jobs(connection, limit: int = 50) -> list[dict]:
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT * FROM integration_events
            WHERE provider = %s
            ORDER BY created_at DESC, id DESC LIMIT %s
            """,
            (PROVIDER, limit),
        )
        return [_decode(row) for row in cursor.fetchall()]
    finally:
        cursor.close()


def list_recoverable_jobs(connection, now: datetime, limit: int = 100) -> list[dict]:
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT * FROM integration_events
            WHERE provider = %s AND status IN ('scheduled', 'retrying')
              AND next_attempt_at <= %s
            ORDER BY next_attempt_at, id LIMIT %s
            """,
            (PROVIDER, now, limit),
        )
        return [_decode(row) for row in cursor.fetchall()]
    finally:
        cursor.close()


def recover_expired_leases(connection, now: datetime) -> int:
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            UPDATE integration_events
            SET status = 'retrying', last_error = 'Worker lease expired before completion'
            WHERE provider = %s AND status = 'processing' AND next_attempt_at <= %s
            """,
            (PROVIDER, now),
        )
        recovered = cursor.rowcount
        connection.commit()
        return recovered
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def claim_job(connection, job_id: int, lease_until: datetime) -> dict | None:
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT * FROM integration_events WHERE id = %s AND provider = %s FOR UPDATE",
            (job_id, PROVIDER),
        )
        job = _decode(cursor.fetchone())
        if job is None or job["status"] not in RUNNABLE_STATUSES:
            connection.rollback()
            return None
        cursor.execute(
            """
            UPDATE integration_events
            SET status = 'processing', attempts = attempts + 1,
                next_attempt_at = %s, last_error = NULL
            WHERE id = %s
            """,
            (lease_until, job_id),
        )
        connection.commit()
        return get_job(connection, job_id)
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def complete_job(connection, job_id: int, completed_at: datetime) -> dict:
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            UPDATE integration_events
            SET status = 'completed', processed_at = %s, next_attempt_at = NULL
            WHERE id = %s AND provider = %s
            """,
            (completed_at, job_id, PROVIDER),
        )
        connection.commit()
        return get_job(connection, job_id)
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def retry_delay_seconds(attempts: int, base_seconds: int, maximum_seconds: int) -> int:
    return min(maximum_seconds, base_seconds * (2 ** max(0, attempts - 1)))


def fail_job(
    connection,
    job_id: int,
    attempts: int,
    error: str,
    now: datetime,
    max_attempts: int,
    base_seconds: int,
    maximum_seconds: int,
) -> dict:
    dead_letter = attempts >= max_attempts
    next_attempt_at = None if dead_letter else now + timedelta(
        seconds=retry_delay_seconds(attempts, base_seconds, maximum_seconds)
    )
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            UPDATE integration_events
            SET status = %s, next_attempt_at = %s, last_error = %s
            WHERE id = %s AND provider = %s
            """,
            (
                "dead_letter" if dead_letter else "retrying",
                next_attempt_at,
                error[:255],
                job_id,
                PROVIDER,
            ),
        )
        connection.commit()
        return get_job(connection, job_id)
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def retry_dead_letter(connection, job_id: int, now: datetime) -> dict | None:
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            UPDATE integration_events
            SET status = 'scheduled', attempts = 0, next_attempt_at = %s, last_error = NULL
            WHERE id = %s AND provider = %s AND status = 'dead_letter'
            """,
            (now, job_id, PROVIDER),
        )
        if cursor.rowcount == 0:
            connection.rollback()
            return None
        connection.commit()
        return get_job(connection, job_id)
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def status_counts(connection) -> dict[str, int]:
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT status, COUNT(*) AS count FROM integration_events
            WHERE provider = %s GROUP BY status
            """,
            (PROVIDER,),
        )
        return {row["status"]: row["count"] for row in cursor.fetchall()}
    finally:
        cursor.close()
