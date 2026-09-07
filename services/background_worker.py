import os
from datetime import datetime, timedelta, timezone

from repositories import job_repository, reminder_repository


REMINDER_SCAN_JOB = "operational_reminder_scan"


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def reminder_scan_key(now: datetime, interval_seconds: int) -> str:
    bucket = int(now.replace(tzinfo=timezone.utc).timestamp()) // interval_seconds
    return f"reminder-scan:{interval_seconds}:{bucket}"


def ensure_reminder_scan_job(connection, queue, now: datetime, interval_seconds: int) -> dict:
    job, created = job_repository.create_job(
        connection,
        REMINDER_SCAN_JOB,
        reminder_scan_key(now, interval_seconds),
        {"scheduled_by": "worker", "interval_seconds": interval_seconds},
        now,
    )
    if created or job["status"] in job_repository.RUNNABLE_STATUSES:
        queue.schedule(job["id"], job["next_attempt_at"] or now)
    return job


def recover_jobs(connection, queue, now: datetime) -> int:
    job_repository.recover_expired_leases(connection, now)
    jobs = job_repository.list_recoverable_jobs(connection, now)
    for job in jobs:
        queue.schedule(job["id"], job["next_attempt_at"] or now)
    return len(jobs)


def process_due_job(connection, queue, now: datetime) -> dict | None:
    job_id = queue.pop_due(now)
    if job_id is None:
        return None
    lease_until = now + timedelta(seconds=int(os.getenv("WORKER_LEASE_SECONDS", "60")))
    job = job_repository.claim_job(connection, job_id, lease_until)
    if job is None:
        return None
    try:
        if job["event_type"] == REMINDER_SCAN_JOB:
            reminder_repository.scan_operational_reminders(connection, None, now)
        else:
            raise ValueError(f"Unsupported background job: {job['event_type']}")
        return job_repository.complete_job(connection, job_id, now)
    except Exception as exc:
        failed = job_repository.fail_job(
            connection,
            job_id,
            job["attempts"],
            f"{type(exc).__name__}: {exc}",
            now,
            max_attempts=int(os.getenv("WORKER_MAX_ATTEMPTS", "5")),
            base_seconds=int(os.getenv("WORKER_RETRY_BASE_SECONDS", "10")),
            maximum_seconds=int(os.getenv("WORKER_RETRY_MAX_SECONDS", "900")),
        )
        if failed["status"] == "retrying":
            queue.schedule(job_id, failed["next_attempt_at"])
        return failed
