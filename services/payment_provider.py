from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import uuid4


@dataclass(frozen=True)
class PaymentInitiation:
    provider_transaction_id: str
    status: str
    provider_payload: dict


class PaymentProvider(Protocol):
    name: str

    def initiate(self, amount: Decimal, currency: str, idempotency_key: str) -> PaymentInitiation:
        ...


class MockPaymentProvider:
    name = "mockpay"

    def initiate(self, amount: Decimal, currency: str, idempotency_key: str) -> PaymentInitiation:
        transaction_id = f"mock_{uuid4().hex}"
        return PaymentInitiation(
            provider_transaction_id=transaction_id,
            status="processing",
            provider_payload={
                "mode": "local-simulation",
                "amount": str(amount),
                "currency": currency,
                "idempotency_key": idempotency_key,
            },
        )


PROVIDERS: dict[str, PaymentProvider] = {"mockpay": MockPaymentProvider()}


def get_payment_provider(name: str) -> PaymentProvider:
    try:
        return PROVIDERS[name]
    except KeyError as exc:
        raise ValueError(f"Unsupported payment provider: {name}") from exc
