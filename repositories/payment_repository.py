import json
from datetime import datetime, timezone
from uuid import uuid4

from models.payment import PaymentStatus
from services.payment_provider import get_payment_provider
from services.workflow import ensure_payment_transition


class PaymentConflict(ValueError):
    pass


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _audit(cursor, actor_id, entity_type, entity_id, action, before=None, after=None):
    cursor.execute(
        """
        INSERT INTO audit_logs(actor_id, entity_type, entity_id, action, before_data, after_data)
        VALUES (%s, %s, %s, %s, %s, %s)
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


def get_order(connection, order_id: int, cursor=None) -> dict | None:
    owns_cursor = cursor is None
    cursor = cursor or connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM orders WHERE id = %s", (order_id,))
        return cursor.fetchone()
    finally:
        if owns_cursor:
            cursor.close()


def list_orders(connection, member_id: int | None = None) -> list[dict]:
    cursor = connection.cursor(dictionary=True)
    try:
        if member_id:
            cursor.execute(
                "SELECT * FROM orders WHERE member_id = %s ORDER BY updated_at DESC",
                (member_id,),
            )
        else:
            cursor.execute("SELECT * FROM orders ORDER BY updated_at DESC LIMIT 100")
        return cursor.fetchall()
    finally:
        cursor.close()


def create_order(connection, quote_id: int, idempotency_key: str, actor_id: int) -> tuple[dict, bool]:
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM orders WHERE idempotency_key = %s", (idempotency_key,))
        existing = cursor.fetchone()
        if existing:
            if existing["quote_id"] != quote_id:
                raise PaymentConflict("Idempotency key was already used for a different quote")
            return existing, False

        cursor.execute(
            """
            SELECT q.id, q.status, q.currency, q.total, tr.member_id
            FROM quotes q
            JOIN trips t ON t.id = q.trip_id
            JOIN travel_requests tr ON tr.id = t.request_id
            WHERE q.id = %s
            FOR UPDATE
            """,
            (quote_id,),
        )
        quote = cursor.fetchone()
        if quote is None:
            raise LookupError("Quote not found")
        if quote["status"] != "approved":
            raise PaymentConflict("Only an approved quote can become an order")

        cursor.execute("SELECT * FROM orders WHERE quote_id = %s", (quote_id,))
        existing_for_quote = cursor.fetchone()
        if existing_for_quote:
            raise PaymentConflict("This quote already has an order; reuse its original idempotency key")

        order_number = f"O-{datetime.now(timezone.utc):%Y%m%d}-{uuid4().hex[:10].upper()}"
        cursor.execute(
            """
            INSERT INTO orders(
                quote_id, member_id, order_number, idempotency_key,
                status, currency, total
            ) VALUES (%s, %s, %s, %s, 'pending_payment', %s, %s)
            """,
            (
                quote_id,
                quote["member_id"],
                order_number,
                idempotency_key,
                quote["currency"],
                quote["total"],
            ),
        )
        order_id = cursor.lastrowid
        order = get_order(connection, order_id, cursor=cursor)
        _audit(cursor, actor_id, "order", order_id, "created", after=order)
        connection.commit()
        return order, True
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def get_payment(connection, payment_id: int, cursor=None) -> dict | None:
    owns_cursor = cursor is None
    cursor = cursor or connection.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT id, order_id, attempt_number, provider, provider_transaction_id,
                   status, amount, currency, initiated_by, failure_code,
                   failure_message, processed_at, created_at, updated_at
            FROM payments WHERE id = %s
            """,
            (payment_id,),
        )
        return cursor.fetchone()
    finally:
        if owns_cursor:
            cursor.close()


def list_payments(connection, order_id: int) -> list[dict]:
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT id, order_id, attempt_number, provider, provider_transaction_id,
                   status, amount, currency, initiated_by, failure_code,
                   failure_message, processed_at, created_at, updated_at
            FROM payments WHERE order_id = %s ORDER BY attempt_number DESC
            """,
            (order_id,),
        )
        return cursor.fetchall()
    finally:
        cursor.close()


def create_payment_attempt(
    connection,
    order_id: int,
    provider_name: str,
    idempotency_key: str,
    actor_id: int,
) -> tuple[dict, bool]:
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT id, order_id, provider FROM payments WHERE idempotency_key = %s",
            (idempotency_key,),
        )
        existing = cursor.fetchone()
        if existing:
            if existing["order_id"] != order_id or existing["provider"] != provider_name:
                raise PaymentConflict(
                    "Idempotency key was already used for a different payment request"
                )
            return get_payment(connection, existing["id"], cursor=cursor), False

        cursor.execute("SELECT * FROM orders WHERE id = %s FOR UPDATE", (order_id,))
        order = cursor.fetchone()
        if order is None:
            raise LookupError("Order not found")
        if order["status"] != "pending_payment":
            raise PaymentConflict(f"Cannot pay an order in {order['status']} status")

        cursor.execute(
            """
            SELECT id, status FROM payments
            WHERE order_id = %s
            ORDER BY attempt_number DESC
            LIMIT 1 FOR UPDATE
            """,
            (order_id,),
        )
        latest_payment = cursor.fetchone()
        if latest_payment and latest_payment["status"] in {"created", "processing"}:
            raise PaymentConflict(
                "This order already has a payment in progress; reuse its original idempotency key"
            )

        cursor.execute(
            "SELECT COALESCE(MAX(attempt_number), 0) + 1 AS next_attempt FROM payments WHERE order_id = %s",
            (order_id,),
        )
        attempt_number = cursor.fetchone()["next_attempt"]
        provider = get_payment_provider(provider_name)
        initiation = provider.initiate(order["total"], order["currency"], idempotency_key)
        cursor.execute(
            """
            INSERT INTO payments(
                order_id, attempt_number, provider, provider_transaction_id,
                idempotency_key, status, amount, currency, initiated_by, provider_payload
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                order_id,
                attempt_number,
                provider.name,
                initiation.provider_transaction_id,
                idempotency_key,
                initiation.status,
                order["total"],
                order["currency"],
                actor_id,
                _json(initiation.provider_payload),
            ),
        )
        payment_id = cursor.lastrowid
        payment = get_payment(connection, payment_id, cursor=cursor)
        _audit(cursor, actor_id, "payment", payment_id, "initiated", after=payment)
        connection.commit()
        return payment, True
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def process_payment_event(
    connection,
    provider: str,
    event: dict,
    actor_id: int | None = None,
) -> bool:
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT id, status FROM integration_events WHERE idempotency_key = %s",
            (event["event_id"],),
        )
        if cursor.fetchone():
            return True

        cursor.execute(
            """
            INSERT INTO integration_events(
                provider, event_type, external_id, idempotency_key, status, payload, attempts
            ) VALUES (%s, 'payment_status', %s, %s, 'received', %s, 1)
            """,
            (provider, event["event_id"], event["event_id"], _json(event)),
        )
        integration_event_id = cursor.lastrowid
        cursor.execute("SELECT * FROM payments WHERE id = %s FOR UPDATE", (event["payment_id"],))
        payment = cursor.fetchone()
        if payment is None:
            raise LookupError("Payment not found")
        if payment["provider"] != provider:
            raise PaymentConflict("Payment provider mismatch")
        if payment["provider_transaction_id"] != event["provider_transaction_id"]:
            raise PaymentConflict("Provider transaction mismatch")

        before = get_payment(connection, payment["id"], cursor=cursor)
        new_status = event["status"]
        if payment["status"] == "succeeded" and new_status == "failed":
            cursor.execute(
                "UPDATE integration_events SET status = 'ignored', processed_at = NOW() WHERE id = %s",
                (integration_event_id,),
            )
            connection.commit()
            return False

        ensure_payment_transition(payment["status"], PaymentStatus(new_status))

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        cursor.execute(
            """
            UPDATE payments
            SET status = %s, failure_code = %s, failure_message = %s, processed_at = %s
            WHERE id = %s
            """,
            (
                new_status,
                event.get("failure_code"),
                event.get("failure_message"),
                now,
                payment["id"],
            ),
        )
        if new_status == "succeeded":
            cursor.execute(
                """
                UPDATE orders SET status = 'paid', paid_at = %s, version = version + 1
                WHERE id = %s AND status = 'pending_payment'
                """,
                (now, payment["order_id"]),
            )
        cursor.execute(
            "UPDATE integration_events SET status = 'processed', processed_at = %s WHERE id = %s",
            (now, integration_event_id),
        )
        after = get_payment(connection, payment["id"], cursor=cursor)
        _audit(cursor, actor_id, "payment", payment["id"], "status_changed", before, after)
        connection.commit()
        return False
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
