from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, EmailStr, Field, model_validator


class MemberStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class MemberTier(StrEnum):
    STANDARD = "standard"
    PREMIUM = "premium"
    VIP = "vip"


class TravelRequestStatus(StrEnum):
    NEW = "new"
    QUALIFIED = "qualified"
    PLANNING = "planning"
    PROPOSAL_READY = "proposal_ready"
    CLIENT_REVIEW = "client_review"
    APPROVED = "approved"
    BOOKED = "booked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TaskStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TaskPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class TripStatus(StrEnum):
    DRAFT = "draft"
    REVIEW = "review"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class TripItemType(StrEnum):
    HOTEL = "hotel"
    FLIGHT = "flight"
    TRANSFER = "transfer"
    ACTIVITY = "activity"
    DINING = "dining"
    OTHER = "other"


class QuoteStatus(StrEnum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class MemberCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    locale: str = Field(default="zh-TW", max_length=16)
    tier: MemberTier = MemberTier.STANDARD
    source: str | None = Field(default=None, max_length=64)
    notes: str | None = None
    travel_styles: list[str] = Field(default_factory=list)
    dietary_restrictions: list[str] = Field(default_factory=list)
    room_preferences: list[str] = Field(default_factory=list)
    accessibility_needs: list[str] = Field(default_factory=list)


class MemberUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    locale: str | None = Field(default=None, max_length=16)
    tier: MemberTier | None = None
    status: MemberStatus | None = None
    source: str | None = Field(default=None, max_length=64)
    notes: str | None = None


class MemberResponse(BaseModel):
    id: int
    owner_id: int | None
    name: str
    email: EmailStr | None
    phone: str | None
    locale: str
    tier: MemberTier
    status: MemberStatus
    source: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class TravelRequestCreate(BaseModel):
    member_id: int
    title: str = Field(min_length=1, max_length=160)
    destination: str = Field(min_length=1, max_length=160)
    start_date: date | None = None
    end_date: date | None = None
    party_size: int = Field(default=1, ge=1, le=100)
    budget_currency: str = Field(default="TWD", min_length=3, max_length=3)
    budget_amount: Decimal | None = Field(default=None, ge=0)
    requirements: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must not be earlier than start_date")
        return self


class TravelRequestUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    destination: str | None = Field(default=None, min_length=1, max_length=160)
    start_date: date | None = None
    end_date: date | None = None
    party_size: int | None = Field(default=None, ge=1, le=100)
    budget_currency: str | None = Field(default=None, min_length=3, max_length=3)
    budget_amount: Decimal | None = Field(default=None, ge=0)
    requirements: dict | None = None
    status: TravelRequestStatus | None = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must not be earlier than start_date")
        return self


class TravelRequestResponse(BaseModel):
    id: int
    member_id: int
    advisor_id: int | None
    title: str
    destination: str
    start_date: date | None
    end_date: date | None
    party_size: int
    budget_currency: str
    budget_amount: Decimal | None
    status: TravelRequestStatus
    requirements: dict
    ai_summary: str | None
    version: int
    created_at: datetime
    updated_at: datetime


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    description: str | None = None
    member_id: int | None = None
    request_id: int | None = None
    assignee_id: int | None = None
    priority: TaskPriority = TaskPriority.NORMAL
    due_at: datetime | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    assignee_id: int | None = None
    priority: TaskPriority | None = None
    due_at: datetime | None = None
    status: TaskStatus | None = None


class TaskResponse(BaseModel):
    id: int
    member_id: int | None
    request_id: int | None
    assignee_id: int | None
    created_by: int
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    due_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TripCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must not be earlier than start_date")
        return self


class TripUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    start_date: date | None = None
    end_date: date | None = None
    status: TripStatus | None = None


class TripResponse(BaseModel):
    id: int
    request_id: int
    name: str
    status: TripStatus
    start_date: date | None
    end_date: date | None
    version: int
    created_at: datetime
    updated_at: datetime


class TripItemCreate(BaseModel):
    item_type: TripItemType
    title: str = Field(min_length=1, max_length=160)
    supplier_name: str | None = Field(default=None, max_length=160)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    location: str | None = Field(default=None, max_length=255)
    unit_price: Decimal | None = Field(default=None, ge=0)
    quantity: int = Field(default=1, ge=1, le=100)
    source_payload: dict = Field(default_factory=dict)
    sort_order: int = Field(default=0, ge=0)


class TripItemUpdate(BaseModel):
    item_type: TripItemType | None = None
    title: str | None = Field(default=None, min_length=1, max_length=160)
    supplier_name: str | None = Field(default=None, max_length=160)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    location: str | None = Field(default=None, max_length=255)
    unit_price: Decimal | None = Field(default=None, ge=0)
    quantity: int | None = Field(default=None, ge=1, le=100)
    source_payload: dict | None = None
    sort_order: int | None = Field(default=None, ge=0)


class TripItemResponse(BaseModel):
    id: int
    trip_id: int
    item_type: TripItemType
    title: str
    supplier_name: str | None
    starts_at: datetime | None
    ends_at: datetime | None
    location: str | None
    unit_price: Decimal | None
    quantity: int
    source_payload: dict
    sort_order: int
    created_at: datetime


class TripDetailResponse(TripResponse):
    items: list[TripItemResponse]


class QuoteCreate(BaseModel):
    tax_rate: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    expires_at: datetime | None = None
    notes: str | None = None


class QuoteItemResponse(BaseModel):
    id: int
    quote_id: int
    source_trip_item_id: int | None
    item_type: str
    title: str
    description: str | None
    unit_price: Decimal
    quantity: int
    line_total: Decimal
    sort_order: int
    created_at: datetime


class QuoteResponse(BaseModel):
    id: int
    trip_id: int
    parent_quote_id: int | None
    quote_number: str
    version: int
    status: QuoteStatus
    currency: str
    subtotal: Decimal
    tax: Decimal
    total: Decimal
    expires_at: datetime | None
    notes: str | None
    approved_by: int | None
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class QuoteDetailResponse(QuoteResponse):
    items: list[QuoteItemResponse]


class QuoteUpdate(BaseModel):
    status: QuoteStatus
