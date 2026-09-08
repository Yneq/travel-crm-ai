import json
from datetime import datetime, timedelta, timezone
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
    effective_status = row.pop("effective_status", None) if row is not None else None
    if effective_status:
        row["status"] = effective_status
    elif (
        row is not None
        and row.get("status") == "pending"
        and row.get("expires_at")
        and row["expires_at"] <= datetime.now(timezone.utc).replace(tzinfo=None)
    ):
        row["status"] = "expired"
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
                    ai_run_id, idempotency_key, action_type, action_payload, expires_at, created_by
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    run_id,
                    f"agent-proposal-{run_id}-{index}-{candidate['action_payload']['source_id']}",
                    candidate["action_type"],
                    json.dumps(candidate["action_payload"], ensure_ascii=False, default=str),
                    datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=24),
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


def list_action_proposals(
    connection,
    status: str | None = None,
    search: str | None = None,
    assigned_to: int | None = None,
    unassigned: bool = False,
    limit: int = 8,
    offset: int = 0,
) -> dict:
    cursor = connection.cursor(dictionary=True)
    try:
        search_pattern = f"%{(search or '').strip()}%"
        where = """
            WHERE (%s IS NULL OR effective_status = %s)
              AND (%s IS NULL OR assigned_to = %s)
              AND (%s = 0 OR assigned_to IS NULL)
              AND (
                %s = '%'
                OR JSON_UNQUOTE(JSON_EXTRACT(action_payload, '$.title')) LIKE %s
                OR JSON_UNQUOTE(JSON_EXTRACT(action_payload, '$.description')) LIKE %s
                OR JSON_UNQUOTE(JSON_EXTRACT(action_payload, '$.order_number')) LIKE %s
              )
        """
        parameters = (
            status, status, assigned_to, assigned_to, int(unassigned),
            search_pattern, search_pattern, search_pattern, search_pattern
        )
        source = """
            (
              SELECT proposals.*, assignee.name AS assigned_to_name,
                     CASE
                       WHEN status = 'pending' AND expires_at <= UTC_TIMESTAMP() THEN 'expired'
                       ELSE status
                     END AS effective_status
              FROM agent_action_proposals proposals
              LEFT JOIN staff_users assignee ON assignee.id = proposals.assigned_to
            ) filtered_proposals
        """
        cursor.execute(f"SELECT COUNT(*) AS total FROM {source} {where}", parameters)
        total = cursor.fetchone()["total"]
        cursor.execute(
            f"""
            SELECT * FROM {source}
            {where}
            ORDER BY effective_status = 'pending' DESC, created_at DESC
            LIMIT %s OFFSET %s
            """,
            (*parameters, limit, offset),
        )
        return {
            "items": [_decode_proposal(row) for row in cursor.fetchall()],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    finally:
        cursor.close()


def proposal_sla_metrics(connection, actor_id: int) -> dict:
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT
              SUM(status = 'pending' AND expires_at > UTC_TIMESTAMP()) AS pending,
              SUM(status = 'pending' AND expires_at > UTC_TIMESTAMP()
                  AND assigned_to IS NULL) AS unassigned,
              SUM(status = 'pending' AND expires_at > UTC_TIMESTAMP()
                  AND expires_at <= UTC_TIMESTAMP() + INTERVAL 4 HOUR) AS expiring_within_4h,
              SUM(status = 'expired'
                  OR (status = 'pending' AND expires_at <= UTC_TIMESTAMP())) AS expired,
              SUM(status = 'pending' AND expires_at > UTC_TIMESTAMP()
                  AND assigned_to = %s) AS assigned_to_me,
              AVG(CASE WHEN reviewed_at IS NOT NULL
                  THEN TIMESTAMPDIFF(MINUTE, created_at, reviewed_at) END) AS average_review_minutes
            FROM agent_action_proposals
            """,
            (actor_id,),
        )
        row = cursor.fetchone() or {}
        average = row.get("average_review_minutes")
        return {
            "pending": int(row.get("pending") or 0),
            "unassigned": int(row.get("unassigned") or 0),
            "expiring_within_4h": int(row.get("expiring_within_4h") or 0),
            "expired": int(row.get("expired") or 0),
            "assigned_to_me": int(row.get("assigned_to_me") or 0),
            "average_review_minutes": round(float(average), 1) if average is not None else None,
        }
    finally:
        cursor.close()


def assign_action_proposals(
    connection,
    proposal_ids: list[int],
    assigned_to: int | None,
    actor_id: int,
) -> dict:
    cursor = connection.cursor(dictionary=True)
    try:
        placeholders = ", ".join(["%s"] * len(proposal_ids))
        cursor.execute(
            f"""
            SELECT id, status, expires_at, assigned_to
            FROM agent_action_proposals
            WHERE id IN ({placeholders})
            FOR UPDATE
            """,
            tuple(proposal_ids),
        )
        proposals = {row["id"]: row for row in cursor.fetchall()}
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        updated_ids = []
        skipped_ids = []
        for proposal_id in proposal_ids:
            proposal = proposals.get(proposal_id)
            eligible = (
                proposal is not None
                and proposal["status"] == "pending"
                and proposal["expires_at"] > now
                and proposal["assigned_to"] != assigned_to
            )
            if not eligible:
                skipped_ids.append(proposal_id)
                continue
            cursor.execute(
                "UPDATE agent_action_proposals SET assigned_to = %s WHERE id = %s",
                (assigned_to, proposal_id),
            )
            cursor.execute(
                """
                INSERT INTO audit_logs(
                    actor_id, entity_type, entity_id, action, before_data, after_data
                ) VALUES (%s, 'agent_action_proposal', %s, 'assignment_changed', %s, %s)
                """,
                (
                    actor_id,
                    str(proposal_id),
                    json.dumps({"assigned_to": proposal["assigned_to"]}),
                    json.dumps({"assigned_to": assigned_to}),
                ),
            )
            updated_ids.append(proposal_id)
        connection.commit()
        return {
            "updated_ids": updated_ids,
            "skipped_ids": skipped_ids,
            "assigned_to": assigned_to,
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


class ActionProposalConflict(ValueError):
    pass


class ActionProposalExpired(ActionProposalConflict):
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
        proposal = cursor.fetchone()
        if proposal is None:
            raise LookupError("Action proposal not found")
        if proposal["status"] != "pending":
            raise ActionProposalConflict("Action proposal has already been reviewed")
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if proposal["expires_at"] <= now:
            cursor.execute(
                """
                UPDATE agent_action_proposals
                SET status = 'expired', reviewed_at = %s
                WHERE id = %s
                """,
                (now, proposal_id),
            )
            cursor.execute(
                """
                INSERT INTO audit_logs(actor_id, entity_type, entity_id, action, after_data)
                VALUES (%s, 'agent_action_proposal', %s, 'expired', %s)
                """,
                (
                    actor_id,
                    str(proposal_id),
                    json.dumps({"expired_at": now.isoformat()}, ensure_ascii=False),
                ),
            )
            connection.commit()
            raise ActionProposalExpired("Action proposal has expired")
        proposal = _decode_proposal(proposal)
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
    except ActionProposalExpired:
        raise
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
