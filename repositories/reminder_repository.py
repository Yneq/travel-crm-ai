import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from services.reminder_rules import build_operational_reminder
from services.followup_provider import generate_followup_with_fallback


class FollowUpConflict(ValueError):
    pass


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _decode(row: dict | None) -> dict | None:
    if row is None:
        return None
    payload = row.get("payload")
    row["payload"] = json.loads(payload) if isinstance(payload, str) else (payload or {})
    ai_draft = row.get("ai_draft")
    row["ai_draft"] = json.loads(ai_draft) if isinstance(ai_draft, str) else ai_draft
    return row


def _audit(cursor, actor_id: int | None, reminder: dict, action: str) -> None:
    cursor.execute(
        """
        INSERT INTO audit_logs(actor_id, entity_type, entity_id, action, after_data)
        VALUES (%s, 'reminder', %s, %s, %s)
        """,
        (actor_id, str(reminder["id"]), action, _json(reminder)),
    )


def get_reminder(connection, reminder_id: int, cursor=None) -> dict | None:
    owns_cursor = cursor is None
    cursor = cursor or connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM reminders WHERE id = %s", (reminder_id,))
        return _decode(cursor.fetchone())
    finally:
        if owns_cursor:
            cursor.close()


def list_reminders(connection, status: str | None, limit: int, offset: int) -> list[dict]:
    cursor = connection.cursor(dictionary=True)
    try:
        if status:
            cursor.execute(
                """
                SELECT * FROM reminders WHERE status = %s
                ORDER BY scheduled_at, created_at DESC LIMIT %s OFFSET %s
                """,
                (status, limit, offset),
            )
        else:
            cursor.execute(
                """
                SELECT * FROM reminders
                ORDER BY status = 'scheduled' DESC, scheduled_at, created_at DESC
                LIMIT %s OFFSET %s
                """,
                (limit, offset),
            )
        return [_decode(row) for row in cursor.fetchall()]
    finally:
        cursor.close()


def _collect_signals(cursor, now: datetime) -> list[dict]:
    signals: list[dict] = []
    cursor.execute(
        """
        SELECT id AS source_id, member_id, title, due_at
        FROM tasks
        WHERE status IN ('open', 'in_progress')
          AND due_at IS NOT NULL
          AND due_at <= %s
        """,
        (now + timedelta(hours=24),),
    )
    signals.extend({"signal_type": "task_due", **row} for row in cursor.fetchall())

    cursor.execute(
        """
        SELECT id AS source_id, member_id, order_number, total, currency, created_at
        FROM orders
        WHERE status = 'pending_payment' AND created_at <= %s
        """,
        (now - timedelta(hours=24),),
    )
    signals.extend({"signal_type": "payment_follow_up", **row} for row in cursor.fetchall())

    cursor.execute(
        """
        SELECT id AS source_id, member_id, title, destination, start_date
        FROM travel_requests
        WHERE status IN ('approved', 'booked')
          AND start_date BETWEEN %s AND %s
        """,
        (now.date(), (now + timedelta(days=14)).date()),
    )
    signals.extend({"signal_type": "trip_countdown", **row} for row in cursor.fetchall())
    return signals


def scan_operational_reminders(connection, actor_id: int | None, now: datetime) -> dict:
    cursor = connection.cursor(dictionary=True)
    created: list[dict] = []
    existing_count = 0
    try:
        for signal in _collect_signals(cursor, now):
            draft = build_operational_reminder(signal, now)
            cursor.execute(
                """
                INSERT IGNORE INTO reminders(
                    task_id, member_id, reminder_type, source_type, source_id,
                    dedup_key, title, channel, scheduled_at, payload
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'internal', %s, %s)
                """,
                (
                    draft["task_id"], draft["member_id"], draft["reminder_type"],
                    draft["source_type"], draft["source_id"], draft["dedup_key"],
                    draft["title"], draft["scheduled_at"], _json(draft["payload"]),
                ),
            )
            if cursor.rowcount == 0:
                existing_count += 1
                continue
            reminder = get_reminder(connection, cursor.lastrowid, cursor=cursor)
            _audit(cursor, actor_id, reminder, "generated")
            created.append(reminder)
        connection.commit()
        return {
            "created_count": len(created),
            "existing_count": existing_count,
            "scanned_at": now,
            "reminders": created,
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def update_reminder_status(
    connection, reminder_id: int, target: str, actor_id: int, reviewed_at: datetime
) -> dict | None:
    cursor = connection.cursor(dictionary=True)
    try:
        current = get_reminder(connection, reminder_id, cursor=cursor)
        if current is None:
            return None
        cursor.execute(
            """
            UPDATE reminders
            SET status = %s, reviewed_by = %s, reviewed_at = %s
            WHERE id = %s
            """,
            (target, actor_id, reviewed_at, reminder_id),
        )
        reminder = get_reminder(connection, reminder_id, cursor=cursor)
        _audit(cursor, actor_id, reminder, f"status_changed_to_{target}")
        connection.commit()
        return reminder
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def _followup_context(cursor, reminder: dict) -> dict:
    member = None
    if reminder.get("member_id"):
        cursor.execute(
            "SELECT name, tier, locale FROM members WHERE id = %s AND deleted_at IS NULL",
            (reminder["member_id"],),
        )
        member = cursor.fetchone()
    payload = reminder.get("payload") or {}
    return {
        "member": member,
        "reminder": {
            "type": reminder["reminder_type"],
            "title": reminder["title"],
            "reason": payload.get("reason", "需要人工確認"),
            "recommended_action": payload.get("recommended_action", "檢查 CRM 最新狀態"),
            "severity": payload.get("severity", "normal"),
        },
    }


def create_followup_draft(
    connection, reminder_id: int, idempotency_key: str, actor_id: int
) -> tuple[dict, bool]:
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM reminders WHERE id = %s FOR UPDATE", (reminder_id,))
        reminder = _decode(cursor.fetchone())
        if reminder is None:
            raise LookupError("Reminder not found")
        if reminder.get("ai_draft"):
            if reminder.get("ai_idempotency_key") != idempotency_key:
                raise FollowUpConflict("This reminder already has an AI follow-up draft")
            return reminder, False
        if reminder["status"] != "scheduled":
            raise FollowUpConflict("Only a scheduled reminder can create a follow-up draft")

        provider_name = os.getenv(
            "AI_FOLLOWUP_PROVIDER", os.getenv("AI_PLANNING_PROVIDER", "local")
        )
        context = _followup_context(cursor, reminder)
        draft, actual_provider = generate_followup_with_fallback(context, provider_name)
        draft["requires_human_review"] = True
        generated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        cursor.execute(
            """
            UPDATE reminders
            SET ai_idempotency_key = %s, ai_provider = %s, ai_draft = %s,
                ai_draft_status = 'awaiting_review', ai_generated_at = %s
            WHERE id = %s
            """,
            (idempotency_key, actual_provider, _json(draft), generated_at, reminder_id),
        )
        updated = get_reminder(connection, reminder_id, cursor=cursor)
        _audit(cursor, actor_id, updated, "ai_followup_draft_created")
        connection.commit()
        return updated, True
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def review_followup_draft(
    connection, reminder_id: int, decision: str, notes: str | None, actor_id: int
) -> dict:
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM reminders WHERE id = %s FOR UPDATE", (reminder_id,))
        reminder = _decode(cursor.fetchone())
        if reminder is None:
            raise LookupError("Reminder not found")
        if reminder.get("ai_draft_status") != "awaiting_review":
            raise FollowUpConflict("AI follow-up draft is not awaiting review")
        target = "approved" if decision == "approve" else "rejected"
        reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        cursor.execute(
            """
            UPDATE reminders
            SET ai_draft_status = %s, ai_reviewed_by = %s,
                ai_reviewed_at = %s, ai_review_notes = %s
            WHERE id = %s
            """,
            (target, actor_id, reviewed_at, notes, reminder_id),
        )
        updated = get_reminder(connection, reminder_id, cursor=cursor)
        _audit(cursor, actor_id, updated, f"ai_followup_draft_{target}")
        connection.commit()
        return updated
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
