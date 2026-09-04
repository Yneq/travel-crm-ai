import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _db_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (dict, list)):
        return _json(value)
    return value


def _decode_json(row: dict | None, *fields: str) -> dict | None:
    if row is None:
        return None
    for field in fields:
        value = row.get(field)
        if isinstance(value, str):
            row[field] = json.loads(value)
        elif value is None:
            row[field] = {}
    return row


def _audit(
    cursor,
    actor_id: int,
    entity_type: str,
    entity_id: int,
    action: str,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    cursor.execute(
        """
        INSERT INTO audit_logs(
            actor_id, entity_type, entity_id, action, before_data, after_data
        ) VALUES (%s, %s, %s, %s, %s, %s)
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


def _update_row(cursor, table: str, entity_id: int, changes: dict) -> None:
    allowed_tables = {"members", "travel_requests", "tasks"}
    if table not in allowed_tables:
        raise ValueError("Unsupported table")
    assignments = ", ".join(f"{column} = %s" for column in changes)
    values = [_db_value(value) for value in changes.values()]
    cursor.execute(
        f"UPDATE {table} SET {assignments} WHERE id = %s",
        (*values, entity_id),
    )


def create_member(connection, payload: dict, actor_id: int) -> dict:
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            INSERT INTO members(owner_id, name, email, phone, locale, tier, source, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                actor_id,
                payload["name"],
                payload.get("email"),
                payload.get("phone"),
                payload["locale"],
                _db_value(payload["tier"]),
                payload.get("source"),
                payload.get("notes"),
            ),
        )
        member_id = cursor.lastrowid
        cursor.execute(
            """
            INSERT INTO member_preferences(
                member_id, travel_styles, dietary_restrictions,
                room_preferences, accessibility_needs
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            (
                member_id,
                _json(payload["travel_styles"]),
                _json(payload["dietary_restrictions"]),
                _json(payload["room_preferences"]),
                _json(payload["accessibility_needs"]),
            ),
        )
        member = get_member(connection, member_id, cursor=cursor)
        _audit(cursor, actor_id, "member", member_id, "created", after=member)
        connection.commit()
        return member
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def get_member(connection, member_id: int, cursor=None) -> dict | None:
    owns_cursor = cursor is None
    cursor = cursor or connection.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT * FROM members WHERE id = %s AND deleted_at IS NULL",
            (member_id,),
        )
        return cursor.fetchone()
    finally:
        if owns_cursor:
            cursor.close()


def list_members(
    connection,
    status: str | None,
    search: str | None,
    limit: int,
    offset: int,
) -> list[dict]:
    cursor = connection.cursor(dictionary=True)
    try:
        clauses = ["deleted_at IS NULL"]
        values: list[Any] = []
        if status:
            clauses.append("status = %s")
            values.append(status)
        if search:
            clauses.append("(name LIKE %s OR email LIKE %s OR phone LIKE %s)")
            keyword = f"%{search}%"
            values.extend([keyword, keyword, keyword])
        values.extend([limit, offset])
        cursor.execute(
            f"""
            SELECT * FROM members
            WHERE {' AND '.join(clauses)}
            ORDER BY updated_at DESC
            LIMIT %s OFFSET %s
            """,
            tuple(values),
        )
        return cursor.fetchall()
    finally:
        cursor.close()


def update_member(connection, member_id: int, changes: dict, actor_id: int) -> dict | None:
    cursor = connection.cursor(dictionary=True)
    try:
        before = get_member(connection, member_id, cursor=cursor)
        if before is None:
            return None
        _update_row(cursor, "members", member_id, changes)
        after = get_member(connection, member_id, cursor=cursor)
        _audit(cursor, actor_id, "member", member_id, "updated", before, after)
        connection.commit()
        return after
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def create_travel_request(connection, payload: dict, actor_id: int) -> dict:
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT id FROM members WHERE id = %s AND deleted_at IS NULL",
            (payload["member_id"],),
        )
        if cursor.fetchone() is None:
            raise LookupError("Member not found")
        cursor.execute(
            """
            INSERT INTO travel_requests(
                member_id, advisor_id, title, destination, start_date, end_date,
                party_size, budget_currency, budget_amount, requirements
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                payload["member_id"],
                actor_id,
                payload["title"],
                payload["destination"],
                payload.get("start_date"),
                payload.get("end_date"),
                payload["party_size"],
                payload["budget_currency"].upper(),
                payload.get("budget_amount"),
                _json(payload["requirements"]),
            ),
        )
        request_id = cursor.lastrowid
        request = get_travel_request(connection, request_id, cursor=cursor)
        _audit(cursor, actor_id, "travel_request", request_id, "created", after=request)
        connection.commit()
        return request
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def get_travel_request(connection, request_id: int, cursor=None) -> dict | None:
    owns_cursor = cursor is None
    cursor = cursor or connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM travel_requests WHERE id = %s", (request_id,))
        return _decode_json(cursor.fetchone(), "requirements")
    finally:
        if owns_cursor:
            cursor.close()


def list_travel_requests(
    connection,
    status: str | None,
    member_id: int | None,
    limit: int,
    offset: int,
) -> list[dict]:
    cursor = connection.cursor(dictionary=True)
    try:
        clauses = ["1 = 1"]
        values: list[Any] = []
        if status:
            clauses.append("status = %s")
            values.append(status)
        if member_id:
            clauses.append("member_id = %s")
            values.append(member_id)
        values.extend([limit, offset])
        cursor.execute(
            f"""
            SELECT * FROM travel_requests
            WHERE {' AND '.join(clauses)}
            ORDER BY updated_at DESC
            LIMIT %s OFFSET %s
            """,
            tuple(values),
        )
        return [_decode_json(row, "requirements") for row in cursor.fetchall()]
    finally:
        cursor.close()


def update_travel_request(
    connection,
    request_id: int,
    changes: dict,
    actor_id: int,
) -> dict | None:
    cursor = connection.cursor(dictionary=True)
    try:
        before = get_travel_request(connection, request_id, cursor=cursor)
        if before is None:
            return None
        changes["version"] = before["version"] + 1
        if changes.get("budget_currency"):
            changes["budget_currency"] = changes["budget_currency"].upper()
        _update_row(cursor, "travel_requests", request_id, changes)
        after = get_travel_request(connection, request_id, cursor=cursor)
        _audit(cursor, actor_id, "travel_request", request_id, "updated", before, after)
        connection.commit()
        return after
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def create_task(connection, payload: dict, actor_id: int) -> dict:
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            INSERT INTO tasks(
                member_id, request_id, assignee_id, created_by, title,
                description, priority, due_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                payload.get("member_id"),
                payload.get("request_id"),
                payload.get("assignee_id") or actor_id,
                actor_id,
                payload["title"],
                payload.get("description"),
                _db_value(payload["priority"]),
                payload.get("due_at"),
            ),
        )
        task_id = cursor.lastrowid
        task = get_task(connection, task_id, cursor=cursor)
        _audit(cursor, actor_id, "task", task_id, "created", after=task)
        connection.commit()
        return task
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def get_task(connection, task_id: int, cursor=None) -> dict | None:
    owns_cursor = cursor is None
    cursor = cursor or connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM tasks WHERE id = %s", (task_id,))
        return cursor.fetchone()
    finally:
        if owns_cursor:
            cursor.close()


def list_tasks(
    connection,
    status: str | None,
    assignee_id: int | None,
    limit: int,
    offset: int,
) -> list[dict]:
    cursor = connection.cursor(dictionary=True)
    try:
        clauses = ["1 = 1"]
        values: list[Any] = []
        if status:
            clauses.append("status = %s")
            values.append(status)
        if assignee_id:
            clauses.append("assignee_id = %s")
            values.append(assignee_id)
        values.extend([limit, offset])
        cursor.execute(
            f"""
            SELECT * FROM tasks
            WHERE {' AND '.join(clauses)}
            ORDER BY due_at IS NULL, due_at, updated_at DESC
            LIMIT %s OFFSET %s
            """,
            tuple(values),
        )
        return cursor.fetchall()
    finally:
        cursor.close()


def update_task(connection, task_id: int, changes: dict, actor_id: int) -> dict | None:
    cursor = connection.cursor(dictionary=True)
    try:
        before = get_task(connection, task_id, cursor=cursor)
        if before is None:
            return None
        if changes.get("status") == "completed" or getattr(changes.get("status"), "value", None) == "completed":
            changes["completed_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
        elif "status" in changes:
            changes["completed_at"] = None
        _update_row(cursor, "tasks", task_id, changes)
        after = get_task(connection, task_id, cursor=cursor)
        _audit(cursor, actor_id, "task", task_id, "updated", before, after)
        connection.commit()
        return after
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
