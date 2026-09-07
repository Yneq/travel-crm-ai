import json
from datetime import datetime, timezone

from services.communication_provider import get_communication_provider
from services.communication_policy import MakerCheckerConflict, ensure_independent_approver
from services.communication_templates import render_template
from models.communication import CommunicationStatus
from services.workflow import ensure_communication_transition


class CommunicationConflict(ValueError):
    pass


COMMUNICATION_SELECT = """
    SELECT cd.*,
           creator.name AS created_by_name,
           editor.name AS last_edited_by_name,
           approver.name AS approved_by_name,
           sender.name AS sent_by_name
    FROM communication_drafts cd
    JOIN staff_users creator ON creator.id = cd.created_by
    JOIN staff_users editor ON editor.id = cd.last_edited_by
    LEFT JOIN staff_users approver ON approver.id = cd.approved_by
    LEFT JOIN staff_users sender ON sender.id = cd.sent_by
"""


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _decode(row: dict | None) -> dict | None:
    if row is not None and isinstance(row.get("provider_payload"), str):
        row["provider_payload"] = json.loads(row["provider_payload"])
    return row


def _audit(cursor, actor_id: int, draft: dict, action: str) -> None:
    cursor.execute(
        """
        INSERT INTO audit_logs(actor_id, entity_type, entity_id, action, after_data)
        VALUES (%s, 'communication_draft', %s, %s, %s)
        """,
        (actor_id, str(draft["id"]), action, _json(draft)),
    )


def _record_version(
    cursor, draft: dict, actor_id: int, source: str, source_template_id: int | None = None
) -> None:
    cursor.execute(
        """
        INSERT INTO communication_draft_versions(
            communication_draft_id, version, subject, body, edited_by,
            source, source_template_id
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            draft["id"], draft["version"], draft["subject"], draft["body"],
            actor_id, source, source_template_id,
        ),
    )


def get_draft(connection, draft_id: int, cursor=None) -> dict | None:
    owns_cursor = cursor is None
    cursor = cursor or connection.cursor(dictionary=True)
    try:
        cursor.execute(f"{COMMUNICATION_SELECT} WHERE cd.id = %s", (draft_id,))
        return _decode(cursor.fetchone())
    finally:
        if owns_cursor:
            cursor.close()


def list_drafts(connection, limit: int = 100) -> list[dict]:
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            f"{COMMUNICATION_SELECT} ORDER BY cd.updated_at DESC, cd.id DESC LIMIT %s",
            (limit,),
        )
        return [_decode(row) for row in cursor.fetchall()]
    finally:
        cursor.close()


def list_templates(connection) -> list[dict]:
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT * FROM communication_templates
            WHERE is_active = TRUE
            ORDER BY name, version DESC
            """
        )
        return cursor.fetchall()
    finally:
        cursor.close()


def list_versions(connection, draft_id: int) -> list[dict]:
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id FROM communication_drafts WHERE id = %s", (draft_id,))
        if cursor.fetchone() is None:
            raise LookupError("Communication draft not found")
        cursor.execute(
            """
            SELECT cdv.*, editor.name AS edited_by_name,
                   template.name AS source_template_name
            FROM communication_draft_versions cdv
            JOIN staff_users editor ON editor.id = cdv.edited_by
            LEFT JOIN communication_templates template
                ON template.id = cdv.source_template_id
            WHERE cdv.communication_draft_id = %s
            ORDER BY cdv.version DESC
            """,
            (draft_id,),
        )
        return cursor.fetchall()
    finally:
        cursor.close()


def create_from_reminder(connection, reminder_id: int, actor_id: int) -> tuple[dict, bool]:
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM reminders WHERE id = %s FOR UPDATE", (reminder_id,))
        reminder = cursor.fetchone()
        if reminder is None:
            raise LookupError("Reminder not found")
        cursor.execute(f"{COMMUNICATION_SELECT} WHERE cd.reminder_id = %s", (reminder_id,))
        existing = _decode(cursor.fetchone())
        if existing:
            connection.commit()
            return existing, False
        if reminder.get("ai_draft_status") != "approved" or not reminder.get("ai_draft"):
            raise CommunicationConflict("An approved AI follow-up draft is required")
        ai_draft = reminder["ai_draft"]
        if isinstance(ai_draft, str):
            ai_draft = json.loads(ai_draft)
        recipient_label = f"Member #{reminder['member_id']}" if reminder.get("member_id") else "Unassigned traveler"
        if reminder.get("member_id"):
            cursor.execute("SELECT name FROM members WHERE id = %s", (reminder["member_id"],))
            member = cursor.fetchone()
            if member:
                recipient_label = member["name"]
        cursor.execute(
            """
            INSERT INTO communication_drafts(
                reminder_id, member_id, recipient_label, subject, body,
                created_by, last_edited_by
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                reminder_id, reminder.get("member_id"), recipient_label,
                ai_draft["message_subject"], ai_draft["message_body"], actor_id, actor_id,
            ),
        )
        draft = get_draft(connection, cursor.lastrowid, cursor=cursor)
        _record_version(cursor, draft, actor_id, "ai_followup")
        _audit(cursor, actor_id, draft, "created_from_ai_followup")
        connection.commit()
        return draft, True
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def update_draft(connection, draft_id: int, subject: str, body: str, actor_id: int) -> dict:
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM communication_drafts WHERE id = %s FOR UPDATE", (draft_id,))
        current = _decode(cursor.fetchone())
        if current is None:
            raise LookupError("Communication draft not found")
        if current["status"] == "sent":
            raise CommunicationConflict("A sent communication cannot be edited")
        ensure_communication_transition(current["status"], CommunicationStatus.DRAFT)
        cursor.execute(
            """
            UPDATE communication_drafts
            SET subject = %s, body = %s, status = 'draft', version = version + 1,
                approved_by = NULL, approved_at = NULL, last_edited_by = %s
            WHERE id = %s
            """,
            (subject, body, actor_id, draft_id),
        )
        draft = get_draft(connection, draft_id, cursor=cursor)
        _record_version(cursor, draft, actor_id, "manual_edit")
        _audit(cursor, actor_id, draft, "edited_and_approval_reset")
        connection.commit()
        return draft
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def apply_template(
    connection, draft_id: int, template_id: int, actor_id: int
) -> dict:
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM communication_drafts WHERE id = %s FOR UPDATE", (draft_id,))
        current = _decode(cursor.fetchone())
        if current is None:
            raise LookupError("Communication draft not found")
        if current["status"] == "sent":
            raise CommunicationConflict("A sent communication cannot be edited")

        cursor.execute(
            "SELECT * FROM communication_templates WHERE id = %s AND is_active = TRUE",
            (template_id,),
        )
        template = cursor.fetchone()
        if template is None:
            raise LookupError("Active communication template not found")

        cursor.execute("SELECT title, payload FROM reminders WHERE id = %s", (current["reminder_id"],))
        reminder = cursor.fetchone()
        payload = reminder.get("payload") or {}
        if isinstance(payload, str):
            payload = json.loads(payload)
        context = {
            "member_name": current["recipient_label"],
            "reminder_title": reminder["title"],
            "recommended_action": payload.get("recommended_action", "請確認最新進度"),
        }
        subject = render_template(template["subject_template"], context)
        body = render_template(template["body_template"], context)
        if len(subject) > 160 or len(body) > 5000:
            raise CommunicationConflict("Rendered template exceeds communication limits")

        ensure_communication_transition(current["status"], CommunicationStatus.DRAFT)
        cursor.execute(
            """
            UPDATE communication_drafts
            SET subject = %s, body = %s, status = 'draft', version = version + 1,
                approved_by = NULL, approved_at = NULL, last_edited_by = %s
            WHERE id = %s
            """,
            (subject, body, actor_id, draft_id),
        )
        draft = get_draft(connection, draft_id, cursor=cursor)
        _record_version(cursor, draft, actor_id, "template", template_id)
        _audit(cursor, actor_id, draft, f"template_applied:{template['template_key']}:v{template['version']}")
        connection.commit()
        return draft
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def approve_draft(connection, draft_id: int, actor_id: int) -> dict:
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM communication_drafts WHERE id = %s FOR UPDATE", (draft_id,))
        current = _decode(cursor.fetchone())
        if current is None:
            raise LookupError("Communication draft not found")
        if current["status"] != "draft":
            raise CommunicationConflict("Only a draft communication can be approved")
        try:
            ensure_independent_approver(actor_id, current["last_edited_by"])
        except MakerCheckerConflict as exc:
            raise CommunicationConflict(str(exc)) from exc
        ensure_communication_transition(current["status"], CommunicationStatus.APPROVED)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        cursor.execute(
            "UPDATE communication_drafts SET status = 'approved', approved_by = %s, approved_at = %s WHERE id = %s",
            (actor_id, now, draft_id),
        )
        draft = get_draft(connection, draft_id, cursor=cursor)
        _audit(cursor, actor_id, draft, "approved_for_mock_send")
        connection.commit()
        return draft
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def send_draft(
    connection, draft_id: int, idempotency_key: str, actor_id: int
) -> tuple[dict, bool]:
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM communication_drafts WHERE id = %s FOR UPDATE", (draft_id,))
        current = _decode(cursor.fetchone())
        if current is None:
            raise LookupError("Communication draft not found")
        if current["status"] == "sent":
            if current.get("send_idempotency_key") != idempotency_key:
                raise CommunicationConflict("Communication was already sent with a different idempotency key")
            connection.commit()
            return current, False
        if current["status"] != "approved":
            raise CommunicationConflict("Communication must be approved before mock send")
        ensure_communication_transition(current["status"], CommunicationStatus.SENT)
        provider = get_communication_provider(current["provider"])
        delivery = provider.send(current["recipient_label"], current["subject"], current["body"])
        sent_at = datetime.now(timezone.utc).replace(tzinfo=None)
        cursor.execute(
            """
            UPDATE communication_drafts
            SET status = 'sent', sent_by = %s, sent_at = %s,
                send_idempotency_key = %s, provider_message_id = %s, provider_payload = %s
            WHERE id = %s
            """,
            (
                actor_id, sent_at, idempotency_key, delivery.provider_message_id,
                _json(delivery.payload), draft_id,
            ),
        )
        draft = get_draft(connection, draft_id, cursor=cursor)
        _audit(cursor, actor_id, draft, "mock_sent")
        connection.commit()
        return draft, True
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
