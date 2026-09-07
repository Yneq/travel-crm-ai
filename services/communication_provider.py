from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4


@dataclass(frozen=True)
class CommunicationDelivery:
    provider_message_id: str
    payload: dict


class CommunicationProvider(Protocol):
    name: str

    def send(self, recipient_label: str, subject: str, body: str) -> CommunicationDelivery:
        ...


class MockEmailProvider:
    """Local-only delivery adapter. It never opens a network connection."""

    name = "mock-email"

    def send(self, recipient_label: str, subject: str, body: str) -> CommunicationDelivery:
        return CommunicationDelivery(
            provider_message_id=f"mock_msg_{uuid4().hex}",
            payload={
                "mode": "local-simulation",
                "recipient_label": recipient_label,
                "subject": subject,
                "body_length": len(body),
                "network_delivery": False,
            },
        )


PROVIDERS: dict[str, CommunicationProvider] = {"mock-email": MockEmailProvider()}


def get_communication_provider(name: str) -> CommunicationProvider:
    try:
        return PROVIDERS[name]
    except KeyError as exc:
        raise ValueError(f"Unsupported communication provider: {name}") from exc
