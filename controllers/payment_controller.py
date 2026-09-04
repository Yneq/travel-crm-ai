import hashlib
import hmac
import os
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import ValidationError

from dependencies import get_current_user, get_db_connection, require_roles
from models.payment import (
    MockPaymentResult,
    OrderResponse,
    PaymentCreate,
    PaymentResponse,
    PaymentWebhookEvent,
    WebhookResult,
)
from repositories import payment_repository as repository


router = APIRouter(prefix="/api", tags=["orders and payments"])
order_write_access = require_roles("admin", "advisor")
payment_write_access = require_roles("admin", "advisor", "finance")


def _translate_repository_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, repository.PaymentConflict):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=422, detail=str(exc))


@router.post(
    "/quotes/{quote_id}/orders",
    status_code=status.HTTP_201_CREATED,
    response_model=OrderResponse,
)
def create_order(
    quote_id: int,
    response: Response,
    idempotency_key: str = Header(min_length=8, max_length=128, alias="Idempotency-Key"),
    connection=Depends(get_db_connection),
    current_user: dict = Depends(order_write_access),
):
    try:
        order, created = repository.create_order(
            connection, quote_id, idempotency_key, current_user["id"]
        )
    except (LookupError, repository.PaymentConflict, ValueError) as exc:
        raise _translate_repository_error(exc) from exc
    if not created:
        response.status_code = status.HTTP_200_OK
    return order


@router.get("/orders", response_model=list[OrderResponse])
def list_orders(
    member_id: int | None = None,
    connection=Depends(get_db_connection),
    _current_user: dict = Depends(get_current_user),
):
    return repository.list_orders(connection, member_id)


@router.get("/orders/{order_id}", response_model=OrderResponse)
def get_order(
    order_id: int,
    connection=Depends(get_db_connection),
    _current_user: dict = Depends(get_current_user),
):
    order = repository.get_order(connection, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.post(
    "/orders/{order_id}/payments",
    status_code=status.HTTP_201_CREATED,
    response_model=PaymentResponse,
)
def create_payment(
    order_id: int,
    payload: PaymentCreate,
    response: Response,
    idempotency_key: str = Header(min_length=8, max_length=128, alias="Idempotency-Key"),
    connection=Depends(get_db_connection),
    current_user: dict = Depends(payment_write_access),
):
    try:
        payment, created = repository.create_payment_attempt(
            connection,
            order_id,
            payload.provider.value,
            idempotency_key,
            current_user["id"],
        )
    except (LookupError, repository.PaymentConflict, ValueError) as exc:
        raise _translate_repository_error(exc) from exc
    if not created:
        response.status_code = status.HTTP_200_OK
    return payment


@router.get("/orders/{order_id}/payments", response_model=list[PaymentResponse])
def list_payments(
    order_id: int,
    connection=Depends(get_db_connection),
    _current_user: dict = Depends(get_current_user),
):
    if repository.get_order(connection, order_id) is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return repository.list_payments(connection, order_id)


@router.post("/payments/{payment_id}/simulate", response_model=PaymentResponse)
def simulate_payment_result(
    payment_id: int,
    payload: MockPaymentResult,
    connection=Depends(get_db_connection),
    current_user: dict = Depends(require_roles("admin")),
):
    if os.getenv("ENABLE_MOCK_PAYMENT", "false").lower() != "true":
        raise HTTPException(status_code=404, detail="Mock payment simulation is disabled")
    payment = repository.get_payment(connection, payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment["provider"] != "mockpay":
        raise HTTPException(status_code=409, detail="Only MockPay payments can be simulated")
    event = PaymentWebhookEvent(
        event_id=f"simulation_{uuid4().hex}",
        payment_id=payment_id,
        provider_transaction_id=payment["provider_transaction_id"],
        status=payload.status,
        failure_code=payload.failure_code,
        failure_message=payload.failure_message,
    )
    try:
        repository.process_payment_event(
            connection, "mockpay", event.model_dump(), current_user["id"]
        )
    except (LookupError, repository.PaymentConflict, ValueError) as exc:
        raise _translate_repository_error(exc) from exc
    return repository.get_payment(connection, payment_id)


@router.post("/webhooks/payments/{provider}", response_model=WebhookResult)
async def payment_webhook(
    provider: str,
    request: Request,
    x_webhook_signature: str = Header(alias="X-Webhook-Signature"),
    connection=Depends(get_db_connection),
):
    if provider != "mockpay":
        raise HTTPException(status_code=404, detail="Unsupported webhook provider")
    secret = os.getenv("MOCKPAY_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(status_code=503, detail="Webhook secret is not configured")
    raw_body = await request.body()
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, x_webhook_signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    try:
        event = PaymentWebhookEvent.model_validate_json(raw_body)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    try:
        duplicate = repository.process_payment_event(connection, provider, event.model_dump())
    except (LookupError, repository.PaymentConflict, ValueError) as exc:
        raise _translate_repository_error(exc) from exc
    return WebhookResult(duplicate=duplicate)
