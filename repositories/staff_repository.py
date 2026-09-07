import json

from services.staff_policy import StaffPolicyConflict, ensure_staff_change_allowed


class StaffConflict(ValueError):
    pass


STAFF_SELECT = """
    SELECT su.id, su.name, su.email, su.is_active, su.created_at, su.updated_at,
           r.code AS role
    FROM staff_users su
    JOIN roles r ON r.id = su.role_id
"""


def list_staff_users(connection) -> list[dict]:
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(f"{STAFF_SELECT} ORDER BY su.is_active DESC, su.name, su.id")
        return cursor.fetchall()
    finally:
        cursor.close()


def update_staff_user(
    connection,
    staff_id: int,
    *,
    role: str | None,
    is_active: bool | None,
    actor_id: int,
) -> dict:
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(f"{STAFF_SELECT} WHERE su.id = %s FOR UPDATE", (staff_id,))
        current = cursor.fetchone()
        if current is None:
            raise LookupError("Staff user not found")

        next_role = role if role is not None else current["role"]
        next_active = is_active if is_active is not None else bool(current["is_active"])
        cursor.execute(
            """
            SELECT COUNT(*) AS total
            FROM staff_users su
            JOIN roles r ON r.id = su.role_id
            WHERE r.code = 'admin' AND su.is_active = TRUE
            """
        )
        active_admin_count = cursor.fetchone()["total"]
        try:
            ensure_staff_change_allowed(
                actor_id=actor_id,
                target_id=staff_id,
                current_role=current["role"],
                current_active=bool(current["is_active"]),
                next_role=next_role,
                next_active=next_active,
                active_admin_count=active_admin_count,
            )
        except StaffPolicyConflict as exc:
            raise StaffConflict(str(exc)) from exc

        cursor.execute("SELECT id FROM roles WHERE code = %s", (next_role,))
        role_row = cursor.fetchone()
        if role_row is None:
            raise StaffConflict("Unknown role")
        cursor.execute(
            "UPDATE staff_users SET role_id = %s, is_active = %s WHERE id = %s",
            (role_row["id"], next_active, staff_id),
        )
        cursor.execute(f"{STAFF_SELECT} WHERE su.id = %s", (staff_id,))
        updated = cursor.fetchone()
        cursor.execute(
            """
            INSERT INTO audit_logs(
                actor_id, entity_type, entity_id, action, before_data, after_data
            ) VALUES (%s, 'staff_user', %s, 'access_updated', %s, %s)
            """,
            (
                actor_id,
                str(staff_id),
                json.dumps(current, ensure_ascii=False, default=str),
                json.dumps(updated, ensure_ascii=False, default=str),
            ),
        )
        connection.commit()
        return updated
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
