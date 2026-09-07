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
                SELECT o.id, o.member_id, o.order_number, o.total, o.currency, o.created_at,
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


def _decode_proposal(row: dict | None) -> dict | None:
    if row is not None and isinstance(row.get("action_payload"), str):
        row["action_payload"] = json.loads(row["action_payload"])
    return row


def _get_proposal(connection, proposal_id: int, cursor=None) -> dict | None:
    owns_cursor = cursor is None
    cursor = cursor or connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM agent_action_proposals WHERE id = %s", (proposal_id,))
        return _decode_proposal(cursor.fetchone())
    finally:
        if owns_cursor:
            cursor.close()


def complete_run(connection, run_id: int, output: dict, actor_id: int) -> dict:
    cursor = connection.cursor(dictionary=True)
    try:
        candidates = output.pop("action_candidates", [])
        proposals = []
        for index, candidate in enumerate(candidates):
            cursor.execute(
                """
                INSERT INTO agent_action_proposals(
                    ai_run_id, idempotency_key, action_type, action_payload, created_by
                ) VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    run_id,
                    f"agent-proposal-{run_id}-{index}-{candidate['action_payload']['source_id']}",
                    candidate["action_type"],
                    json.dumps(candidate["action_payload"], ensure_ascii=False, default=str),
                    actor_id,
                ),
            )
            proposal = _get_proposal(connection, cursor.lastrowid, cursor=cursor)
            proposal["label"] = candidate["label"]
            proposals.append(proposal)
        output["proposed_actions"] = proposals
        safe_audit_payload = {
            "tools_used": [item["tool"] for item in output["tools_used"]],
            "provider": output["provider"],
            "fallback_used": output["fallback_used"],
            "requires_human_confirmation": True,
            "proposal_count": len(proposals),
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
        return output
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def list_action_proposals(connection, limit: int = 50) -> list[dict]:
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT * FROM agent_action_proposals
            ORDER BY status = 'pending' DESC, created_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        return [_decode_proposal(row) for row in cursor.fetchall()]
    finally:
        cursor.close()


class ActionProposalConflict(ValueError):
    pass


def review_action_proposal(
    connection,
    proposal_id: int,
    decision: str,
    notes: str | None,
    actor_id: int,
) -> dict:
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT * FROM agent_action_proposals WHERE id = %s FOR UPDATE",
            (proposal_id,),
        )
        proposal = _decode_proposal(cursor.fetchone())
        if proposal is None:
            raise LookupError("Action proposal not found")
        if proposal["status"] != "pending":
            raise ActionProposalConflict("Action proposal has already been reviewed")
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if decision == "rejected":
            cursor.execute(
                """
                UPDATE agent_action_proposals
                SET status = 'rejected', reviewed_by = %s, review_notes = %s, reviewed_at = %s
                WHERE id = %s
                """,
                (actor_id, notes, now, proposal_id),
            )
            action = "rejected"
        elif decision == "approved" and proposal["action_type"] == "create_task":
            payload = proposal["action_payload"]
            if payload.get("source_type") == "order":
                cursor.execute(
                    "SELECT status FROM orders WHERE id = %s FOR UPDATE",
                    (payload["source_id"],),
                )
                source_order = cursor.fetchone()
                if source_order is None or source_order["status"] != "pending_payment":
                    raise ActionProposalConflict(
                        "Source order is no longer awaiting payment"
                    )
                cursor.execute(
                    """
                    SELECT id FROM agent_action_proposals
                    WHERE action_type = 'create_task' AND status = 'executed'
                      AND JSON_UNQUOTE(JSON_EXTRACT(action_payload, '$.source_type')) = 'order'
                      AND JSON_UNQUOTE(JSON_EXTRACT(action_payload, '$.source_id')) = %s
                    LIMIT 1
                    """,
                    (str(payload["source_id"]),),
                )
                if cursor.fetchone():
                    raise ActionProposalConflict(
                        "A task was already created from an Agent proposal for this order"
                    )
            cursor.execute(
                """
                INSERT INTO tasks(
                    member_id, assignee_id, created_by, title, description, priority, due_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    payload.get("member_id"), actor_id, actor_id, payload["title"],
                    payload.get("description"), payload.get("priority", "normal"),
                    payload.get("due_at"),
                ),
            )
            task_id = cursor.lastrowid
            cursor.execute(
                """
                UPDATE agent_action_proposals
                SET status = 'executed', reviewed_by = %s, review_notes = %s,
                    reviewed_at = %s, executed_entity_type = 'task', executed_entity_id = %s
                WHERE id = %s
                """,
                (actor_id, notes, now, task_id, proposal_id),
            )
            cursor.execute(
                """
                INSERT INTO audit_logs(actor_id, entity_type, entity_id, action, after_data)
                VALUES (%s, 'task', %s, 'created_from_agent_proposal', %s)
                """,
                (actor_id, str(task_id), json.dumps({"proposal_id": proposal_id}, ensure_ascii=False)),
            )
            action = "executed"
        else:
            raise ActionProposalConflict("Unsupported proposal decision or action type")
        cursor.execute(
            """
            INSERT INTO audit_logs(actor_id, entity_type, entity_id, action, after_data)
            VALUES (%s, 'agent_action_proposal', %s, %s, %s)
            """,
            (actor_id, str(proposal_id), action, json.dumps({"notes": notes}, ensure_ascii=False)),
        )
        reviewed = _get_proposal(connection, proposal_id, cursor=cursor)
        connection.commit()
        return reviewed
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
