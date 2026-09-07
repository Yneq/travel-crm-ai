class MakerCheckerConflict(ValueError):
    pass


def ensure_independent_approver(actor_id: int, last_edited_by: int) -> None:
    if actor_id == last_edited_by:
        raise MakerCheckerConflict(
            "Maker-checker requires a different admin to approve this communication"
        )
