from models.crm import QuoteStatus, TaskStatus, TravelRequestStatus, TripStatus
from models.payment import OrderStatus, PaymentStatus
from models.reminder import ReminderStatus


TRAVEL_REQUEST_TRANSITIONS = {
    TravelRequestStatus.NEW: {TravelRequestStatus.QUALIFIED, TravelRequestStatus.CANCELLED},
    TravelRequestStatus.QUALIFIED: {TravelRequestStatus.PLANNING, TravelRequestStatus.CANCELLED},
    TravelRequestStatus.PLANNING: {TravelRequestStatus.PROPOSAL_READY, TravelRequestStatus.CANCELLED},
    TravelRequestStatus.PROPOSAL_READY: {
        TravelRequestStatus.PLANNING,
        TravelRequestStatus.CLIENT_REVIEW,
        TravelRequestStatus.CANCELLED,
    },
    TravelRequestStatus.CLIENT_REVIEW: {
        TravelRequestStatus.PLANNING,
        TravelRequestStatus.APPROVED,
        TravelRequestStatus.CANCELLED,
    },
    TravelRequestStatus.APPROVED: {TravelRequestStatus.BOOKED, TravelRequestStatus.CANCELLED},
    TravelRequestStatus.BOOKED: {TravelRequestStatus.COMPLETED, TravelRequestStatus.CANCELLED},
    TravelRequestStatus.COMPLETED: set(),
    TravelRequestStatus.CANCELLED: set(),
}

TASK_TRANSITIONS = {
    TaskStatus.OPEN: {TaskStatus.IN_PROGRESS, TaskStatus.COMPLETED, TaskStatus.CANCELLED},
    TaskStatus.IN_PROGRESS: {TaskStatus.OPEN, TaskStatus.COMPLETED, TaskStatus.CANCELLED},
    TaskStatus.COMPLETED: {TaskStatus.OPEN},
    TaskStatus.CANCELLED: {TaskStatus.OPEN},
}

TRIP_TRANSITIONS = {
    TripStatus.DRAFT: {TripStatus.REVIEW, TripStatus.CANCELLED},
    TripStatus.REVIEW: {TripStatus.DRAFT, TripStatus.CONFIRMED, TripStatus.CANCELLED},
    TripStatus.CONFIRMED: {TripStatus.CANCELLED},
    TripStatus.CANCELLED: set(),
}

QUOTE_TRANSITIONS = {
    QuoteStatus.DRAFT: {QuoteStatus.PENDING_APPROVAL, QuoteStatus.CANCELLED},
    QuoteStatus.PENDING_APPROVAL: {
        QuoteStatus.APPROVED,
        QuoteStatus.REJECTED,
        QuoteStatus.CANCELLED,
    },
    QuoteStatus.REJECTED: {QuoteStatus.DRAFT, QuoteStatus.CANCELLED},
    QuoteStatus.APPROVED: set(),
    QuoteStatus.CANCELLED: set(),
}

ORDER_TRANSITIONS = {
    OrderStatus.PENDING_PAYMENT: {OrderStatus.PAID, OrderStatus.CANCELLED},
    OrderStatus.PAID: {OrderStatus.FULFILLED, OrderStatus.REFUNDED},
    OrderStatus.FULFILLED: {OrderStatus.REFUNDED},
    OrderStatus.CANCELLED: set(),
    OrderStatus.REFUNDED: set(),
}

PAYMENT_TRANSITIONS = {
    PaymentStatus.CREATED: {PaymentStatus.PROCESSING, PaymentStatus.FAILED},
    PaymentStatus.PROCESSING: {PaymentStatus.SUCCEEDED, PaymentStatus.FAILED},
    PaymentStatus.SUCCEEDED: {PaymentStatus.REFUNDED},
    PaymentStatus.FAILED: set(),
    PaymentStatus.REFUNDED: set(),
}

REMINDER_TRANSITIONS = {
    ReminderStatus.SCHEDULED: {ReminderStatus.ACKNOWLEDGED, ReminderStatus.DISMISSED},
    ReminderStatus.ACKNOWLEDGED: set(),
    ReminderStatus.DISMISSED: set(),
}


class InvalidTransition(ValueError):
    pass


def ensure_travel_request_transition(current: str, target: TravelRequestStatus) -> None:
    current_status = TravelRequestStatus(current)
    if target == current_status:
        return
    if target not in TRAVEL_REQUEST_TRANSITIONS[current_status]:
        raise InvalidTransition(f"Cannot change travel request from {current_status} to {target}")


def ensure_task_transition(current: str, target: TaskStatus) -> None:
    current_status = TaskStatus(current)
    if target == current_status:
        return
    if target not in TASK_TRANSITIONS[current_status]:
        raise InvalidTransition(f"Cannot change task from {current_status} to {target}")


def ensure_trip_transition(current: str, target: TripStatus) -> None:
    current_status = TripStatus(current)
    if target == current_status:
        return
    if target not in TRIP_TRANSITIONS[current_status]:
        raise InvalidTransition(f"Cannot change trip from {current_status} to {target}")


def ensure_quote_transition(current: str, target: QuoteStatus) -> None:
    current_status = QuoteStatus(current)
    if target == current_status:
        return
    if target not in QUOTE_TRANSITIONS[current_status]:
        raise InvalidTransition(f"Cannot change quote from {current_status} to {target}")


def ensure_order_transition(current: str, target: OrderStatus) -> None:
    current_status = OrderStatus(current)
    if target == current_status:
        return
    if target not in ORDER_TRANSITIONS[current_status]:
        raise InvalidTransition(f"Cannot change order from {current_status} to {target}")


def ensure_payment_transition(current: str, target: PaymentStatus) -> None:
    current_status = PaymentStatus(current)
    if target == current_status:
        return
    if target not in PAYMENT_TRANSITIONS[current_status]:
        raise InvalidTransition(f"Cannot change payment from {current_status} to {target}")


def ensure_reminder_transition(current: str, target: ReminderStatus) -> None:
    current_status = ReminderStatus(current)
    if target == current_status:
        return
    if target not in REMINDER_TRANSITIONS[current_status]:
        raise InvalidTransition(f"Cannot change reminder from {current_status} to {target}")
