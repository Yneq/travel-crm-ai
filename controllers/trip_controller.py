from io import BytesIO
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse

from dependencies import get_current_user, get_db_connection, require_roles
from models.crm import (
    QuoteCreate,
    QuoteDetailResponse,
    QuoteResponse,
    QuoteStatus,
    QuoteUpdate,
    TripCreate,
    TripDetailResponse,
    TripItemCreate,
    TripItemResponse,
    TripItemUpdate,
    TripResponse,
    TripUpdate,
)
from repositories import trip_repository as repository
from services.workflow import (
    InvalidTransition,
    ensure_quote_transition,
    ensure_trip_transition,
)


router = APIRouter(prefix="/api", tags=["trips and quotes"])
write_access = require_roles("admin", "advisor")
logger = logging.getLogger(__name__)


def _not_found(entity: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"{entity} not found")


@router.post(
    "/travel-requests/{request_id}/trips",
    status_code=status.HTTP_201_CREATED,
    response_model=TripResponse,
)
def create_trip(
    request_id: int,
    payload: TripCreate,
    connection=Depends(get_db_connection),
    current_user: dict = Depends(write_access),
):
    try:
        return repository.create_trip(connection, request_id, payload.model_dump(), current_user["id"])
    except LookupError as exc:
        raise _not_found("Travel request") from exc


@router.get("/trips", response_model=list[TripResponse])
def list_trips(
    request_id: int | None = Query(default=None, ge=1),
    connection=Depends(get_db_connection),
    _current_user: dict = Depends(get_current_user),
):
    return repository.list_trips(connection, request_id)


@router.get("/trips/{trip_id}", response_model=TripDetailResponse)
def get_trip(
    trip_id: int,
    connection=Depends(get_db_connection),
    _current_user: dict = Depends(get_current_user),
):
    trip = repository.get_trip(connection, trip_id)
    if trip is None:
        raise _not_found("Trip")
    return trip


@router.patch("/trips/{trip_id}", response_model=TripResponse)
def update_trip(
    trip_id: int,
    payload: TripUpdate,
    connection=Depends(get_db_connection),
    current_user: dict = Depends(write_access),
):
    current = repository.get_trip(connection, trip_id, include_items=False)
    if current is None:
        raise _not_found("Trip")
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="At least one field is required")
    start_date = changes.get("start_date", current["start_date"])
    end_date = changes.get("end_date", current["end_date"])
    if start_date and end_date and end_date < start_date:
        raise HTTPException(status_code=422, detail="end_date must not be earlier than start_date")
    if payload.status is not None:
        try:
            ensure_trip_transition(current["status"], payload.status)
        except InvalidTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    return repository.update_trip(connection, trip_id, changes, current_user["id"])


@router.post(
    "/trips/{trip_id}/items",
    status_code=status.HTTP_201_CREATED,
    response_model=TripItemResponse,
)
def create_trip_item(
    trip_id: int,
    payload: TripItemCreate,
    connection=Depends(get_db_connection),
    current_user: dict = Depends(write_access),
):
    try:
        return repository.create_trip_item(connection, trip_id, payload.model_dump(), current_user["id"])
    except LookupError as exc:
        raise _not_found("Trip") from exc


@router.patch("/trip-items/{item_id}", response_model=TripItemResponse)
def update_trip_item(
    item_id: int,
    payload: TripItemUpdate,
    connection=Depends(get_db_connection),
    current_user: dict = Depends(write_access),
):
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="At least one field is required")
    item = repository.update_trip_item(connection, item_id, changes, current_user["id"])
    if item is None:
        raise _not_found("Trip item")
    return item


@router.delete("/trip-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_trip_item(
    item_id: int,
    connection=Depends(get_db_connection),
    current_user: dict = Depends(write_access),
):
    if not repository.delete_trip_item(connection, item_id, current_user["id"]):
        raise _not_found("Trip item")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/trips/{trip_id}/quotes",
    status_code=status.HTTP_201_CREATED,
    response_model=QuoteDetailResponse,
)
def create_quote(
    trip_id: int,
    payload: QuoteCreate,
    connection=Depends(get_db_connection),
    current_user: dict = Depends(write_access),
):
    try:
        return repository.create_quote(connection, trip_id, payload.model_dump(), current_user["id"])
    except LookupError as exc:
        raise _not_found("Trip") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/quotes", response_model=list[QuoteResponse])
def list_quotes(
    trip_id: int | None = Query(default=None, ge=1),
    connection=Depends(get_db_connection),
    _current_user: dict = Depends(get_current_user),
):
    return repository.list_quotes(connection, trip_id)


@router.get("/quotes/{quote_id}", response_model=QuoteDetailResponse)
def get_quote(
    quote_id: int,
    connection=Depends(get_db_connection),
    _current_user: dict = Depends(get_current_user),
):
    quote = repository.get_quote(connection, quote_id)
    if quote is None:
        raise _not_found("Quote")
    return quote


@router.get(
    "/quotes/{quote_id}/documents/proposal.pdf",
    response_class=StreamingResponse,
    responses={200: {"content": {"application/pdf": {}}}},
)
def download_quote_proposal(
    quote_id: int,
    connection=Depends(get_db_connection),
    _current_user: dict = Depends(get_current_user),
):
    context = repository.get_quote_document_context(connection, quote_id)
    if context is None:
        raise _not_found("Quote")
    if context["status"] != "approved":
        raise HTTPException(status_code=409, detail="Only approved quotes can be downloaded")

    try:
        # Lazy import keeps the rest of the API bootable during an image rebuild.
        from services.quote_pdf import build_quote_proposal_pdf

        content = build_quote_proposal_pdf(context)
    except ModuleNotFoundError as exc:
        logger.exception("PDF dependency is unavailable")
        raise HTTPException(
            status_code=503,
            detail="PDF generator is unavailable; rebuild the API image",
        ) from exc
    except Exception as exc:
        logger.exception("Quote PDF generation failed for quote %s", quote_id)
        raise HTTPException(
            status_code=500,
            detail=f"PDF generation failed ({type(exc).__name__})",
        ) from exc
    filename = f"voyageops-{context['quote_number']}.pdf"
    return StreamingResponse(
        BytesIO(content),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.patch("/quotes/{quote_id}", response_model=QuoteDetailResponse)
def update_quote(
    quote_id: int,
    payload: QuoteUpdate,
    connection=Depends(get_db_connection),
    current_user: dict = Depends(get_current_user),
):
    quote = repository.get_quote(connection, quote_id)
    if quote is None:
        raise _not_found("Quote")

    if payload.status in {QuoteStatus.APPROVED, QuoteStatus.REJECTED}:
        allowed = {"admin", "finance"}
    else:
        allowed = {"admin", "advisor"}
    if current_user.get("role") not in allowed:
        raise HTTPException(status_code=403, detail="Insufficient permissions for this quote transition")

    try:
        ensure_quote_transition(quote["status"], payload.status)
    except InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return repository.update_quote_status(
        connection,
        quote_id,
        payload.status.value,
        current_user["id"],
    )
