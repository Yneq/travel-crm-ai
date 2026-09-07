import json
from datetime import datetime


SENSITIVE_KEY_PARTS = ("password", "token", "secret", "api_key", "authorization")


def redact_audit_data(value):
    if isinstance(value, dict):
        return {
            key: "[REDACTED]"
            if any(part in key.lower() for part in SENSITIVE_KEY_PARTS)
            else redact_audit_data(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_audit_data(item) for item in value]
    return value


def _decode(row: dict) -> dict:
    for key in ("before_data", "after_data"):
        if isinstance(row.get(key), str):
            row[key] = json.loads(row[key])
        row[key] = redact_audit_data(row.get(key))
    return row


def list_audit_logs(
    connection,
    *,
    entity_type: str | None,
    entity_id: str | None,
    action: str | None,
    actor_id: int | None,
    date_from: datetime | None,
    date_to: datetime | None,
    limit: int,
    offset: int,
) -> dict:
    conditions: list[str] = []
    parameters: list[object] = []
    filters = (
        ("al.entity_type = %s", entity_type),
        ("al.entity_id = %s", entity_id),
        ("al.action = %s", action),
        ("al.actor_id = %s", actor_id),
        ("al.created_at >= %s", date_from),
        ("al.created_at <= %s", date_to),
    )
    for clause, value in filters:
        if value is not None:
            conditions.append(clause)
            parameters.append(value)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(f"SELECT COUNT(*) AS total FROM audit_logs al {where}", tuple(parameters))
        total = cursor.fetchone()["total"]
        cursor.execute(
            f"""
            SELECT al.*, actor.name AS actor_name
            FROM audit_logs al
            LEFT JOIN staff_users actor ON actor.id = al.actor_id
            {where}
            ORDER BY al.created_at DESC, al.id DESC
            LIMIT %s OFFSET %s
            """,
            (*parameters, limit, offset),
        )
        return {
            "items": [_decode(row) for row in cursor.fetchall()],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    finally:
        cursor.close()


def get_audit_facets(connection) -> dict:
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT DISTINCT entity_type FROM audit_logs ORDER BY entity_type")
        entity_types = [row["entity_type"] for row in cursor.fetchall()]
        cursor.execute("SELECT DISTINCT action FROM audit_logs ORDER BY action")
        actions = [row["action"] for row in cursor.fetchall()]
        cursor.execute(
            """
            SELECT DISTINCT su.id, su.name
            FROM audit_logs al
            JOIN staff_users su ON su.id = al.actor_id
            ORDER BY su.name, su.id
            """
        )
        return {
            "entity_types": entity_types,
            "actions": actions,
            "actors": cursor.fetchall(),
        }
    finally:
        cursor.close()
