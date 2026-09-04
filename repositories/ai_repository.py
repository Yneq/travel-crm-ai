import json
import os
from datetime import datetime, timezone

from services.ai_planning_graph import run_planning_graph
from services.planning_provider import get_planning_provider


class AIWorkflowConflict(ValueError):
    pass


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _decode_json(row: dict | None) -> dict | None:
    if row is None:
        return None
    for field in ("input_data", "output_data", "error_data"):
        if isinstance(row.get(field), str):
            row[field] = json.loads(row[field])
    return row


def _audit(cursor, actor_id, entity_type, entity_id, action, before=None, after=None):
    cursor.execute(
        """
        INSERT INTO audit_logs(actor_id, entity_type, entity_id, action, before_data, after_data)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            actor_id,
            entity_type,
            str(entity_id),
            action,
            _json(before) if before else None,
            _json(after) if after else None,
        ),
    )


def get_planning_context(connection, request_id: int, cursor=None) -> dict | None:
    owns_cursor = cursor is None
    cursor = cursor or connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM travel_requests WHERE id = %s", (request_id,))
        request = cursor.fetchone()
        if request is None:
            return None
        cursor.execute("SELECT * FROM members WHERE id = %s AND deleted_at IS NULL", (request["member_id"],))
        member = cursor.fetchone()
        if member is None:
            return None
        cursor.execute("SELECT * FROM member_preferences WHERE member_id = %s", (member["id"],))
        preferences = cursor.fetchone() or {}
        if isinstance(request.get("requirements"), str):
            request["requirements"] = json.loads(request["requirements"])
        for field in (
            "travel_styles",
            "dietary_restrictions",
            "room_preferences",
            "accessibility_needs",
        ):
            if isinstance(preferences.get(field), str):
                preferences[field] = json.loads(preferences[field])
            elif preferences.get(field) is None:
                preferences[field] = []
        request_context = {
            field: request.get(field)
            for field in (
                "id",
                "title",
                "destination",
                "start_date",
                "end_date",
                "party_size",
                "budget_currency",
                "budget_amount",
                "requirements",
                "version",
            )
        }
        member_context = {
            field: member.get(field) for field in ("id", "name", "tier", "locale")
        }
        preference_context = {
            field: preferences.get(field, [])
            for field in (
                "travel_styles",
                "dietary_restrictions",
                "room_preferences",
                "accessibility_needs",
            )
        }
        return {
            "request": request_context,
            "member": member_context,
            "preferences": preference_context,
        }
    finally:
        if owns_cursor:
            cursor.close()


def get_ai_plan(connection, run_id: int, cursor=None) -> dict | None:
    owns_cursor = cursor is None
    cursor = cursor or connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM ai_runs WHERE id = %s", (run_id,))
        return _decode_json(cursor.fetchone())
    finally:
        if owns_cursor:
            cursor.close()


def list_ai_plans(connection, request_id: int) -> list[dict]:
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT * FROM ai_runs WHERE request_id = %s ORDER BY started_at DESC, id DESC",
            (request_id,),
        )
        return [_decode_json(row) for row in cursor.fetchall()]
    finally:
        cursor.close()


def create_ai_plan(
    connection,
    request_id: int,
    planning_notes: str | None,
    idempotency_key: str,
    actor_id: int,
) -> tuple[dict, bool]:
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM ai_runs WHERE idempotency_key = %s", (idempotency_key,))
        existing = _decode_json(cursor.fetchone())
        if existing:
            if existing["request_id"] != request_id:
                raise AIWorkflowConflict("Idempotency key was already used for a different request")
            if existing["input_data"].get("planning_notes") != planning_notes:
                raise AIWorkflowConflict("Idempotency key was already used with different planning notes")
            return existing, False

        context = get_planning_context(connection, request_id, cursor=cursor)
        if context is None:
            raise LookupError("Travel request not found")
        provider_name = os.getenv("AI_PLANNING_PROVIDER", "local")
        provider = get_planning_provider(provider_name)
        started_at = datetime.now(timezone.utc).replace(tzinfo=None)
        output = run_planning_graph(context, planning_notes, provider)
        completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        input_data = {
            "request_version": context["request"]["version"],
            "planning_notes": planning_notes,
            "context": context,
        }
        cursor.execute(
            """
            INSERT INTO ai_runs(
                request_id, idempotency_key, initiated_by, workflow_name,
                workflow_version, model_name, status, input_data, output_data,
                started_at, completed_at
            ) VALUES (%s, %s, %s, 'travel_request_to_itinerary', '1.0.0', %s,
                      'awaiting_review', %s, %s, %s, %s)
            """,
            (
                request_id,
                idempotency_key,
                actor_id,
                provider.name,
                _json(input_data),
                _json(output),
                started_at,
                completed_at,
            ),
        )
        run_id = cursor.lastrowid
        run = get_ai_plan(connection, run_id, cursor=cursor)
        _audit(cursor, actor_id, "ai_run", run_id, "draft_created", after=run)
        connection.commit()
        return run, True
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def review_ai_plan(
    connection,
    run_id: int,
    decision: str,
    notes: str | None,
    actor_id: int,
) -> tuple[dict, int | None]:
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM ai_runs WHERE id = %s FOR UPDATE", (run_id,))
        raw_run = cursor.fetchone()
        if raw_run is None:
            raise LookupError("AI plan not found")
        run = _decode_json(raw_run)
        if run["status"] != "awaiting_review":
            raise AIWorkflowConflict(f"AI plan is already {run['status']}")

        reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        trip_id = None
        if decision == "approve":
            cursor.execute("SELECT * FROM travel_requests WHERE id = %s FOR UPDATE", (run["request_id"],))
            request = cursor.fetchone()
            output = run["output_data"]
            cursor.execute(
                """
                INSERT INTO trips(request_id, name, start_date, end_date)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    request["id"],
                    output["draft_name"],
                    request.get("start_date"),
                    request.get("end_date"),
                ),
            )
            trip_id = cursor.lastrowid
            for index, item in enumerate(output["itinerary_items"]):
                cursor.execute(
                    """
                    INSERT INTO trip_items(
                        trip_id, item_type, title, location, quantity,
                        source_payload, sort_order
                    ) VALUES (%s, %s, %s, %s, 1, %s, %s)
                    """,
                    (
                        trip_id,
                        item["item_type"],
                        item["title"],
                        item.get("location"),
                        _json(
                            {
                                "source": "ai_draft",
                                "ai_run_id": run_id,
                                "day": item["day"],
                                "rationale": item["rationale"],
                                "requires_verification": True,
                            }
                        ),
                        index,
                    ),
                )
            cursor.execute(
                "UPDATE travel_requests SET ai_summary = %s, version = version + 1 WHERE id = %s",
                (output["summary"], request["id"]),
            )
            new_status = "applied"
            _audit(cursor, actor_id, "trip", trip_id, "created_from_ai_draft", after={"ai_run_id": run_id})
        else:
            new_status = "rejected"

        cursor.execute(
            """
            UPDATE ai_runs
            SET status = %s, reviewed_by = %s, reviewed_at = %s,
                review_notes = %s, applied_trip_id = %s
            WHERE id = %s
            """,
            (new_status, actor_id, reviewed_at, notes, trip_id, run_id),
        )
        reviewed_run = get_ai_plan(connection, run_id, cursor=cursor)
        _audit(cursor, actor_id, "ai_run", run_id, f"review_{decision}", run, reviewed_run)
        connection.commit()
        return reviewed_run, trip_id
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
