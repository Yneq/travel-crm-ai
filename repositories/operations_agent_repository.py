import json
from datetime import datetime, timezone
from uuid import uuid4


TOOL_LABELS = {
    "operations_overview": "營運總覽",
    "overdue_tasks": "逾期與即將到期任務",
    "payment_followups": "待付款追蹤",
    "upcoming_departures": "近期出發行程",
}


def execute_read_tool(connection, tool_name: str) -> dict:
    cursor = connection.cursor(dictionary=True)
    try:
        if tool_name == "operations_overview":
            cursor.execute(
                """
                SELECT
                  (SELECT COUNT(*) FROM members WHERE deleted_at IS NULL AND status = 'active') AS active_members,
                  (SELECT COUNT(*) FROM travel_requests WHERE status NOT IN ('completed', 'cancelled')) AS active_requests,
                  (SELECT COUNT(*) FROM tasks WHERE status IN ('open', 'in_progress')) AS open_tasks,
                  (SELECT COUNT(*) FROM orders WHERE status = 'pending_payment') AS pending_payments,
                  (SELECT COUNT(*) FROM reminders WHERE status = 'scheduled') AS scheduled_reminders
                """
            )
            return {"summary": cursor.fetchone(), "items": []}
        if tool_name == "overdue_tasks":
            cursor.execute(
                """
                SELECT t.id, t.title, t.priority, t.status, t.due_at, m.name AS member_name
                FROM tasks t
                LEFT JOIN members m ON m.id = t.member_id
                WHERE t.status IN ('open', 'in_progress')
                  AND t.due_at IS NOT NULL
                  AND t.due_at <= UTC_TIMESTAMP() + INTERVAL 24 HOUR
                ORDER BY t.due_at, FIELD(t.priority, 'urgent', 'high', 'normal', 'low')
                LIMIT 10
                """
            )
            return {"items": cursor.fetchall()}
        if tool_name == "payment_followups":
            cursor.execute(
                """
                SELECT o.id, o.order_number, o.total, o.currency, o.created_at,
                       m.name AS member_name
                FROM orders o
                JOIN members m ON m.id = o.member_id
                WHERE o.status = 'pending_payment'
                ORDER BY o.created_at
                LIMIT 10
                """
            )
            return {"items": cursor.fetchall()}
        if tool_name == "upcoming_departures":
            cursor.execute(
                """
                SELECT tr.id, tr.title, tr.destination, tr.start_date, tr.status,
                       m.name AS member_name
                FROM travel_requests tr
                JOIN members m ON m.id = tr.member_id
                WHERE tr.status IN ('approved', 'booked')
                  AND tr.start_date BETWEEN UTC_DATE() AND UTC_DATE() + INTERVAL 30 DAY
                ORDER BY tr.start_date
                LIMIT 10
                """
            )
            return {"items": cursor.fetchall()}
        raise ValueError(f"Unsupported operations tool: {tool_name}")
    finally:
        cursor.close()


def start_run(connection, question: str, initiated_by: int) -> int:
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO ai_runs(
                idempotency_key, initiated_by, workflow_name, workflow_version, model_name,
                status, input_data, started_at
            ) VALUES (%s, %s, 'crm_operations_agent', '1.0', 'langgraph-local',
                      'processing', %s, %s)
            """,
            (
                f"operations-agent-{uuid4()}",
                initiated_by,
                json.dumps({"question": question}, ensure_ascii=False),
                datetime.now(timezone.utc).replace(tzinfo=None),
            ),
        )
        connection.commit()
        return cursor.lastrowid
    finally:
        cursor.close()


def complete_run(connection, run_id: int, output: dict, actor_id: int) -> None:
    cursor = connection.cursor()
    try:
        safe_audit_payload = {
            "tools_used": [item["tool"] for item in output["tools_used"]],
            "provider": output["provider"],
            "fallback_used": output["fallback_used"],
            "requires_human_confirmation": True,
        }
        cursor.execute(
            """
            UPDATE ai_runs
            SET status = 'completed', model_name = %s, output_data = %s, completed_at = %s
            WHERE id = %s
            """,
            (
                output["provider"],
                json.dumps(output, ensure_ascii=False, default=str),
                datetime.now(timezone.utc).replace(tzinfo=None),
                run_id,
            ),
        )
        cursor.execute(
            """
            INSERT INTO audit_logs(actor_id, entity_type, entity_id, action, after_data)
            VALUES (%s, 'ai_run', %s, 'operations_agent_completed', %s)
            """,
            (actor_id, str(run_id), json.dumps(safe_audit_payload, ensure_ascii=False)),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def fail_run(connection, run_id: int, error: Exception) -> None:
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            UPDATE ai_runs
            SET status = 'failed', error_data = %s, completed_at = %s
            WHERE id = %s
            """,
            (
                json.dumps({"type": type(error).__name__}, ensure_ascii=False),
                datetime.now(timezone.utc).replace(tzinfo=None),
                run_id,
            ),
        )
        connection.commit()
    finally:
        cursor.close()
