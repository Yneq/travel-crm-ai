import json
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _db_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (dict, list)):
        return _json(value)
    return value


def _audit(cursor, actor_id: int, entity_type: str, entity_id: int, action: str, before=None, after=None):
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


def _decode_item(row: dict) -> dict:
    value = row.get("source_payload")
    row["source_payload"] = json.loads(value) if isinstance(value, str) else (value or {})
    return row


def create_trip(connection, request_id: int, payload: dict, actor_id: int) -> dict:
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id FROM travel_requests WHERE id = %s", (request_id,))
        if cursor.fetchone() is None:
            raise LookupError("Travel request not found")
        cursor.execute(
            """
            INSERT INTO trips(request_id, name, start_date, end_date)
            VALUES (%s, %s, %s, %s)
            """,
            (request_id, payload["name"], payload.get("start_date"), payload.get("end_date")),
        )
        trip_id = cursor.lastrowid
        trip = get_trip(connection, trip_id, cursor=cursor, include_items=False)
        _audit(cursor, actor_id, "trip", trip_id, "created", after=trip)
        connection.commit()
        return trip
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def get_trip(connection, trip_id: int, cursor=None, include_items: bool = True) -> dict | None:
    owns_cursor = cursor is None
    cursor = cursor or connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM trips WHERE id = %s", (trip_id,))
        trip = cursor.fetchone()
        if trip is None:
            return None
        if include_items:
            cursor.execute(
                "SELECT * FROM trip_items WHERE trip_id = %s ORDER BY sort_order, id",
                (trip_id,),
            )
            trip["items"] = [_decode_item(row) for row in cursor.fetchall()]
        return trip
    finally:
        if owns_cursor:
            cursor.close()


def list_trips(connection, request_id: int | None) -> list[dict]:
    cursor = connection.cursor(dictionary=True)
    try:
        if request_id:
            cursor.execute(
                "SELECT * FROM trips WHERE request_id = %s ORDER BY updated_at DESC",
                (request_id,),
            )
        else:
            cursor.execute("SELECT * FROM trips ORDER BY updated_at DESC LIMIT 100")
        return cursor.fetchall()
    finally:
        cursor.close()


def update_trip(connection, trip_id: int, changes: dict, actor_id: int) -> dict | None:
    cursor = connection.cursor(dictionary=True)
    try:
        before = get_trip(connection, trip_id, cursor=cursor, include_items=False)
        if before is None:
            return None
        changes["version"] = before["version"] + 1
        assignments = ", ".join(f"{field} = %s" for field in changes)
        cursor.execute(
            f"UPDATE trips SET {assignments} WHERE id = %s",
            (*[_db_value(value) for value in changes.values()], trip_id),
        )
        after = get_trip(connection, trip_id, cursor=cursor, include_items=False)
        _audit(cursor, actor_id, "trip", trip_id, "updated", before, after)
        connection.commit()
        return after
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def create_trip_item(connection, trip_id: int, payload: dict, actor_id: int) -> dict:
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id FROM trips WHERE id = %s", (trip_id,))
        if cursor.fetchone() is None:
            raise LookupError("Trip not found")
        cursor.execute(
            """
            INSERT INTO trip_items(
                trip_id, item_type, title, supplier_name, starts_at, ends_at,
                location, unit_price, quantity, source_payload, sort_order
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                trip_id,
                _db_value(payload["item_type"]),
                payload["title"],
                payload.get("supplier_name"),
                payload.get("starts_at"),
                payload.get("ends_at"),
                payload.get("location"),
                payload.get("unit_price"),
                payload["quantity"],
                _json(payload["source_payload"]),
                payload["sort_order"],
            ),
        )
        item_id = cursor.lastrowid
        cursor.execute("UPDATE trips SET version = version + 1 WHERE id = %s", (trip_id,))
        item = get_trip_item(connection, item_id, cursor=cursor)
        _audit(cursor, actor_id, "trip_item", item_id, "created", after=item)
        connection.commit()
        return item
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def get_trip_item(connection, item_id: int, cursor=None) -> dict | None:
    owns_cursor = cursor is None
    cursor = cursor or connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM trip_items WHERE id = %s", (item_id,))
        item = cursor.fetchone()
        return _decode_item(item) if item else None
    finally:
        if owns_cursor:
            cursor.close()


def update_trip_item(connection, item_id: int, changes: dict, actor_id: int) -> dict | None:
    cursor = connection.cursor(dictionary=True)
    try:
        before = get_trip_item(connection, item_id, cursor=cursor)
        if before is None:
            return None
        assignments = ", ".join(f"{field} = %s" for field in changes)
        cursor.execute(
            f"UPDATE trip_items SET {assignments} WHERE id = %s",
            (*[_db_value(value) for value in changes.values()], item_id),
        )
        cursor.execute("UPDATE trips SET version = version + 1 WHERE id = %s", (before["trip_id"],))
        after = get_trip_item(connection, item_id, cursor=cursor)
        _audit(cursor, actor_id, "trip_item", item_id, "updated", before, after)
        connection.commit()
        return after
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def delete_trip_item(connection, item_id: int, actor_id: int) -> bool:
    cursor = connection.cursor(dictionary=True)
    try:
        before = get_trip_item(connection, item_id, cursor=cursor)
        if before is None:
            return False
        cursor.execute("DELETE FROM trip_items WHERE id = %s", (item_id,))
        cursor.execute("UPDATE trips SET version = version + 1 WHERE id = %s", (before["trip_id"],))
        _audit(cursor, actor_id, "trip_item", item_id, "deleted", before=before)
        connection.commit()
        return True
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def create_quote(connection, trip_id: int, payload: dict, actor_id: int) -> dict:
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT t.id, tr.budget_currency
            FROM trips t
            JOIN travel_requests tr ON tr.id = t.request_id
            WHERE t.id = %s
            """,
            (trip_id,),
        )
        trip = cursor.fetchone()
        if trip is None:
            raise LookupError("Trip not found")
        cursor.execute(
            "SELECT * FROM trip_items WHERE trip_id = %s ORDER BY sort_order, id",
            (trip_id,),
        )
        items = cursor.fetchall()
        if not items:
            raise ValueError("Add at least one trip item before creating a quote")
        if any(item["unit_price"] is None for item in items):
            raise ValueError("Every trip item needs a unit_price before creating a quote")

        cursor.execute(
            "SELECT id, version FROM quotes WHERE trip_id = %s ORDER BY version DESC LIMIT 1",
            (trip_id,),
        )
        previous = cursor.fetchone()
        version = (previous["version"] + 1) if previous else 1
        parent_quote_id = previous["id"] if previous else None
        quote_number = f"Q-{trip_id:06d}-V{version:02d}"
        subtotal = sum(
            (Decimal(item["unit_price"]) * item["quantity"] for item in items),
            Decimal("0"),
        ).quantize(Decimal("0.01"))
        tax = (subtotal * Decimal(payload["tax_rate"])).quantize(Decimal("0.01"))
        total = subtotal + tax

        cursor.execute(
            """
            INSERT INTO quotes(
                trip_id, parent_quote_id, quote_number, version, status,
                currency, subtotal, tax, total, expires_at, notes
            ) VALUES (%s, %s, %s, %s, 'draft', %s, %s, %s, %s, %s, %s)
            """,
            (
                trip_id,
                parent_quote_id,
                quote_number,
                version,
                trip["budget_currency"],
                subtotal,
                tax,
                total,
                payload.get("expires_at"),
                payload.get("notes"),
            ),
        )
        quote_id = cursor.lastrowid
        for item in items:
            line_total = (Decimal(item["unit_price"]) * item["quantity"]).quantize(Decimal("0.01"))
            cursor.execute(
                """
                INSERT INTO quote_items(
                    quote_id, source_trip_item_id, item_type, title,
                    unit_price, quantity, line_total, sort_order
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    quote_id,
                    item["id"],
                    item["item_type"],
                    item["title"],
                    item["unit_price"],
                    item["quantity"],
                    line_total,
                    item["sort_order"],
                ),
            )
        quote = get_quote(connection, quote_id, cursor=cursor)
        _audit(cursor, actor_id, "quote", quote_id, "created", after=quote)
        connection.commit()
        return quote
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def get_quote(connection, quote_id: int, cursor=None) -> dict | None:
    owns_cursor = cursor is None
    cursor = cursor or connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM quotes WHERE id = %s", (quote_id,))
        quote = cursor.fetchone()
        if quote is None:
            return None
        cursor.execute(
            "SELECT * FROM quote_items WHERE quote_id = %s ORDER BY sort_order, id",
            (quote_id,),
        )
        quote["items"] = cursor.fetchall()
        return quote
    finally:
        if owns_cursor:
            cursor.close()


def get_quote_document_context(connection, quote_id: int) -> dict | None:
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT
                q.*,
                t.name AS trip_name,
                COALESCE(t.start_date, tr.start_date) AS start_date,
                COALESCE(t.end_date, tr.end_date) AS end_date,
                tr.title AS request_title,
                tr.destination,
                tr.party_size,
                m.name AS member_name,
                approver.name AS approved_by_name
            FROM quotes q
            JOIN trips t ON t.id = q.trip_id
            JOIN travel_requests tr ON tr.id = t.request_id
            JOIN members m ON m.id = tr.member_id
            LEFT JOIN staff_users approver ON approver.id = q.approved_by
            WHERE q.id = %s
            """,
            (quote_id,),
        )
        context = cursor.fetchone()
        if context is None:
            return None
        cursor.execute(
            "SELECT * FROM quote_items WHERE quote_id = %s ORDER BY sort_order, id",
            (quote_id,),
        )
        context["items"] = cursor.fetchall()
        return context
    finally:
        cursor.close()


def list_quotes(connection, trip_id: int | None) -> list[dict]:
    cursor = connection.cursor(dictionary=True)
    try:
        if trip_id:
            cursor.execute(
                "SELECT * FROM quotes WHERE trip_id = %s ORDER BY version DESC",
                (trip_id,),
            )
        else:
            cursor.execute("SELECT * FROM quotes ORDER BY updated_at DESC LIMIT 100")
        return cursor.fetchall()
    finally:
        cursor.close()


def update_quote_status(connection, quote_id: int, target: str, actor_id: int) -> dict | None:
    cursor = connection.cursor(dictionary=True)
    try:
        before = get_quote(connection, quote_id, cursor=cursor)
        if before is None:
            return None
        approved_by = actor_id if target == "approved" else None
        approved_at = datetime.now(timezone.utc).replace(tzinfo=None) if target == "approved" else None
        cursor.execute(
            """
            UPDATE quotes
            SET status = %s, approved_by = %s, approved_at = %s
            WHERE id = %s
            """,
            (target, approved_by, approved_at, quote_id),
        )
        after = get_quote(connection, quote_id, cursor=cursor)
        _audit(cursor, actor_id, "quote", quote_id, "status_changed", before, after)
        connection.commit()
        return after
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
