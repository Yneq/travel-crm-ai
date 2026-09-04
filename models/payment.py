from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field


class OrderStatus(StrEnum):
    PENDING_PAYMENT = "pending_payment"
    PAID = "paid"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class PaymentStatus(StrEnum):
    CREATED = "created"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"


class PaymentProviderName(StrEnum):
    MOCKPAY = "mockpay"


class OrderResponse(BaseModel):
    id: int
    quote_id: int
    member_id: int
    order_number: str
    status: OrderStatus
    version: int
    currency: str
    total: Decimal
    paid_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PaymentCreate(BaseModel):
    provider: PaymentProviderName = PaymentProviderName.MOCKPAY


class PaymentResponse(BaseModel):
    id: int
    order_id: int
    attempt_number: int
    provider: str
    provider_transaction_id: str | None
    status: PaymentStatus
    amount: Decimal
    currency: str
    initiated_by: int | None
    failure_code: str | None
    failure_message: str | None
    processed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class MockPaymentResult(BaseModel):
    status: str = Field(pattern="^(succeeded|failed)$")
    failure_code: str | None = Field(default=None, max_length=64)
    failure_message: str | None = Field(default=None, max_length=255)


class WebhookResult(BaseModel):
    received: bool = True
    duplicate: bool = False


class PaymentWebhookEvent(BaseModel):
    event_id: str = Field(min_length=1, max_length=128)
    payment_id: int
    provider_transaction_id: str = Field(min_length=1, max_length=128)
    status: str = Field(pattern="^(succeeded|failed)$")
    failure_code: str | None = Field(default=None, max_length=64)
    failure_message: str | None = Field(default=None, max_length=255)
