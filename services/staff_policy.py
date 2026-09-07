class StaffPolicyConflict(ValueError):
    pass


def ensure_staff_change_allowed(
    *,
    actor_id: int,
    target_id: int,
    current_role: str,
    current_active: bool,
    next_role: str,
    next_active: bool,
    active_admin_count: int,
) -> None:
    if actor_id == target_id:
        raise StaffPolicyConflict(
            "Administrators cannot change their own role or active status"
        )
    removes_active_admin = current_role == "admin" and current_active and (
        next_role != "admin" or not next_active
    )
    if removes_active_admin and active_admin_count <= 1:
        raise StaffPolicyConflict("At least one active admin must remain")
