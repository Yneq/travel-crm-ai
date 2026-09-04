# VoyageOps AI

**English** | [繁體中文](README.zh-TW.md)

VoyageOps AI is an API-first travel CRM and operations platform evolved from the
Taipei Day Trip booking project. The first milestone focuses on reliable backend
contracts and operational data before introducing model-driven automation.

## Current milestone

- Staff authentication with bcrypt password hashing and JWT bearer tokens
- Role model for `admin`, `advisor`, and `finance`
- Member profiles and ownership
- Travel request intake and lifecycle management
- Versioned trip itineraries and priced itinerary items
- Immutable quote snapshots with approval workflow
- Downloadable Traditional Chinese quote PDFs generated from immutable snapshots
- Idempotent order creation and payment attempts
- Signed, replay-safe payment webhooks with a local MockPay adapter
- Explicit order/payment state machines and audit trails
- LangGraph travel-planning workflow with request summarization, gap detection,
  draft generation, and guardrails
- Human review before an AI draft can create an editable itinerary
- Optional Gemini 3.8 Flash provider with Pydantic structured output and a
  privacy allowlist; local planning remains the default
- Internal task assignment and lifecycle management
- Audit logs for CRM mutations
- Schema foundations for trips, quotes, orders, payments, documents, reminders,
  AI runs, and third-party integration events
- Local MySQL and Redis environment through Docker Compose
- OpenAPI documentation at `/docs`
- Browser-based operations dashboard at `/admin`

The original attraction, booking, payment, and static frontend source remains in
the repository as migration reference, but the new `app.py` exposes only the
VoyageOps API.

## REST API

### Authentication

| Operation | Method | Endpoint |
|---|---:|---|
| Bootstrap the first admin | `POST` | `/api/auth/register` |
| Log in and issue a bearer token | `POST` | `/api/auth/login` |
| Read the authenticated staff user | `GET` | `/api/users/me` |
| Create a staff account (admin only) | `POST` | `/api/staff-users` |

Login uses `POST` because credentials are submitted to create an authentication
result. `PUT` remains appropriate for the legacy presigned S3 upload because
that request writes the object identified by the presigned URL.

Bootstrap registration closes after the first staff account is created. That
first account receives the `admin` role; later staff accounts must be created by
an authenticated admin.

### CRM

| Resource | Method | Endpoint |
|---|---:|---|
| Members | `POST`, `GET` | `/api/members` |
| Member | `GET`, `PATCH` | `/api/members/{member_id}` |
| Travel requests | `POST`, `GET` | `/api/travel-requests` |
| Travel request | `GET`, `PATCH` | `/api/travel-requests/{request_id}` |
| Tasks | `POST`, `GET` | `/api/tasks` |
| Task | `PATCH` | `/api/tasks/{task_id}` |
| Trips | `GET` | `/api/trips` |
| Trip | `GET`, `PATCH` | `/api/trips/{trip_id}` |
| Create trip from request | `POST` | `/api/travel-requests/{request_id}/trips` |
| Trip items | `POST` | `/api/trips/{trip_id}/items` |
| Trip item | `PATCH`, `DELETE` | `/api/trip-items/{item_id}` |
| Quotes | `GET` | `/api/quotes` |
| Create quote snapshot | `POST` | `/api/trips/{trip_id}/quotes` |
| Quote | `GET`, `PATCH` | `/api/quotes/{quote_id}` |
| Download approved quote PDF | `GET` | `/api/quotes/{quote_id}/documents/proposal.pdf` |
| Create order from approved quote | `POST` | `/api/quotes/{quote_id}/orders` |
| Orders | `GET` | `/api/orders` |
| Order | `GET` | `/api/orders/{order_id}` |
| Start payment attempt | `POST` | `/api/orders/{order_id}/payments` |
| Payment history | `GET` | `/api/orders/{order_id}/payments` |
| Simulate MockPay result (local admin only) | `POST` | `/api/payments/{payment_id}/simulate` |
| Payment webhook | `POST` | `/api/webhooks/payments/{provider}` |
| Generate AI plan draft | `POST` | `/api/travel-requests/{request_id}/ai-plans` |
| Request AI plan history | `GET` | `/api/travel-requests/{request_id}/ai-plans` |
| AI plan | `GET` | `/api/ai-plans/{run_id}` |
| Approve or reject AI plan | `POST` | `/api/ai-plans/{run_id}/review` |

Writes require an `admin` or `advisor` role. Authenticated finance users can
read CRM data but cannot change it.

## Workflow rules

Travel requests follow an explicit state machine:

```text
new → qualified → planning → proposal_ready → client_review
                                                ↓
                                             approved → booked → completed
```

Supported stages may transition to `cancelled`; invalid jumps such as
`new → booked` return HTTP `409 Conflict`. Tasks similarly use controlled
`open`, `in_progress`, `completed`, and `cancelled` transitions.

Trips must move through `draft → review → confirmed`. Quotes use
`draft → pending_approval → approved/rejected`; only `admin` or `finance` may
approve or reject. Each quote copies the current itinerary items into
`quote_items`, so later itinerary edits produce a new version without changing
historical quotes.

Creating an order or a payment requires an `Idempotency-Key` header. Reusing
the same key returns the original resource, while a different key cannot create
a second order for the same quote. Only one payment attempt may be processing
for an order at a time; a failed attempt can be retried with a new key.

`MockPay` is a local integration adapter, not a production payment provider.
Its webhook uses an HMAC-SHA256 `X-Webhook-Signature`, stores provider events by
event ID, and ignores late failure events after payment success. A real provider
can replace the adapter while preserving the order and payment API contracts.

## AI planning workflow

The travel planning graph executes four explicit nodes:

```text
prepare_privacy_safe_context → identify_missing_information
→ generate_structured_plan → quality_guardrail
```

Every result is stored as `awaiting_review`. Approval creates a normal editable
trip and copies the proposed items into `trip_items` in one database
transaction. Rejection leaves CRM and itinerary data unchanged. Neither path
creates quotes, orders, or payments automatically.

The default `local-planner` is deterministic and does not call an external LLM,
claim current prices, select suppliers, or check inventory. It provides a safe
local workflow demonstration and a provider boundary for adding a real model
later without changing the review API. AI context excludes member email and
phone fields and retains only information needed for travel planning.

### Enable the Gemini free-tier provider

Create a Gemini Developer API key in Google AI Studio, then put these values in
the project `.env` file (never commit the real key):

```dotenv
AI_PLANNING_PROVIDER=gemini
GEMINI_API_KEY=replace-with-your-key
GEMINI_MODEL=gemini-3.8-flash
GEMINI_FALLBACK_MODEL=gemini-3.5-flash-lite
AI_PROVIDER_TIMEOUT_MS=20000
AI_PROVIDER_MAX_RETRIES=2
AI_PROVIDER_MAX_OUTPUT_TOKENS=8192
```

Recreate only the API service to apply the environment change:

```bash
docker compose up -d --no-build --force-recreate api
```

`gemini-3.8-flash` is the default because it is the latest stable Flash model,
supports structured outputs and agent workflows, and is available on the
Gemini Developer API free tier. Its default medium thinking level is a balanced
choice for this prototype; keep the model configurable so regression cases can
be compared before changing it in a deployed environment.

The provider sends one structured-output request per attempt and retries
transient `429` and `5xx` responses at most twice with exponential backoff. Its
primary model is `gemini-3.8-flash`; after retries are exhausted on a transient
failure—or when structured output fails validation—it falls back to
`gemini-3.5-flash-lite` and records the model that actually produced the stored
draft. The higher output limit leaves room for thinking tokens before the JSON
response. Its
privacy allowlist transmits only traveler name/tier/locale, trip details, and
travel preferences. It does not transmit member email or phone. The free tier
may use submitted content to improve Google products, so do not use real client
data during testing and reassess the data-processing terms before production.

## Run locally

Copy the example environment file if running the API outside containers:

```bash
cp .env.example .env
```

Start the complete local environment:

```bash
docker compose up --build
```

This initializes a fresh `travel_crm` MySQL database, applies the ordered SQL
migrations, and starts Redis and the FastAPI service. If Docker Hub is timing
out but the API image already exists locally, use `docker compose up -d --no-build`.
The Compose API uses Uvicorn reload mode for local development so later Python
changes are picked up automatically; production deployment should run without
`--reload`.

- API: <http://localhost:8080>
- Admin dashboard: <http://localhost:8080/admin>
- Swagger UI: <http://localhost:8080/docs>
- Health check: <http://localhost:8080/health>

The migration runner records file checksums in `schema_migrations`, so existing
volumes receive new migrations without deleting local data. Remove the project
volume only when intentionally resetting all local data.

## Test

```bash
python -m unittest discover -v tests
```

The current suite verifies REST route contracts, health/OpenAPI exposure,
password hashing, JWT round trips, frontend authentication endpoints, payment
provider behavior, PDF generation, schema invariants, and valid or invalid
workflow transitions.

## Next milestone

1. AI planning regression fixtures and provider evaluation
2. Reminder workers and integration retry processing
3. Production payment-provider adapter and secret management
