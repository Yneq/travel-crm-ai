# VoyageOps AI

**English** | [繁體中文](README.zh-TW.md)

VoyageOps AI is an API-first travel CRM and operations platform evolved from the
Taipei Day Trip booking project. It combines reliable backend contracts and
operational data with guarded model-driven automation.

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
- Internal operations reminder center for due tasks, pending payments, and
  upcoming departures, with deduplication and human acknowledgement
- AI Follow-up Copilot for internal summaries, recommended actions, and editable
  traveler-message drafts; approval never sends a message automatically
- Versioned communication drafts with approval reset on edit, maker-checker
  separation, named audit actors, and idempotent local-only Mock Email delivery
- Privacy-safe communication templates and immutable content-version snapshots
- Versioned 12-case AI regression set covering schema, tool selection, guardrails,
  privacy, unsafe operational claims, provider fallback, and latency
- Admin-only Audit Log dashboard with actor/entity/action/date filters, pagination,
  before/after details, and recursive credential redaction
- LangGraph CRM Operations Agent with intent routing, a multi-step read-only tool
  loop, Gemini Function Calling, deterministic fallback, execution traces, and
  human-in-the-loop guardrails
- Human-approved Agent write proposals for internal follow-up tasks, with
  24-hour expiry, required rejection reasons, stale-source validation,
  duplicate-execution protection, atomic audit records, and a searchable,
  status-filtered review queue with pagination, ownership, and bulk triage
- Schema foundations for trips, quotes, orders, payments, documents, reminders,
  AI runs, and third-party integration events
- Independent background worker with Redis scheduled jobs, MySQL recovery,
  exponential retry, and dead-letter handling
- Local MySQL, Redis, API, and worker environment through Docker Compose
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
| List staff accounts and access state (admin only) | `GET` | `/api/staff-users` |
| Change a staff role or active state (admin only) | `PATCH` | `/api/staff-users/{staff_id}` |

Login uses `POST` because credentials are submitted to create an authentication
result. `PUT` remains appropriate for the legacy presigned S3 upload because
that request writes the object identified by the presigned URL.

Bootstrap registration closes after the first staff account is created. That
first account receives the `admin` role; later staff accounts must be created by
an authenticated admin. The Admin UI supports `advisor`, `finance`, and `admin`
roles plus account activation. It blocks self-demotion/self-deactivation and
preserves at least one active administrator. Authorization revalidates the
current database role and active state on every authenticated API request, so a
revoked account cannot continue using an older JWT.

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
| Operations reminders | `GET` | `/api/reminders` |
| Scan current operational risks | `POST` | `/api/reminders/scan` |
| Acknowledge or dismiss reminder | `PATCH` | `/api/reminders/{reminder_id}` |
| Generate AI follow-up draft | `POST` | `/api/reminders/{reminder_id}/ai-draft` |
| Approve or reject follow-up draft | `POST` | `/api/reminders/{reminder_id}/ai-draft/review` |
| Background job history | `GET` | `/api/operations/jobs` |
| Worker and queue status | `GET` | `/api/operations/worker/status` |
| Retry a dead-letter job (admin only) | `POST` | `/api/operations/jobs/{job_id}/retry` |
| Communication drafts | `GET` | `/api/communication-drafts` |
| Create editable draft from approved AI output | `POST` | `/api/reminders/{reminder_id}/communication-draft` |
| Edit communication and reset approval | `PATCH` | `/api/communication-drafts/{draft_id}` |
| Approve communication | `POST` | `/api/communication-drafts/{draft_id}/approve` |
| Execute idempotent Mock Send | `POST` | `/api/communication-drafts/{draft_id}/send` |
| Active communication templates | `GET` | `/api/communication-templates` |
| Apply a template as a new draft version | `POST` | `/api/communication-drafts/{draft_id}/templates/{template_id}` |
| Communication content history | `GET` | `/api/communication-drafts/{draft_id}/versions` |
| Filtered, paginated audit history (admin only) | `GET` | `/api/audit-logs` |
| Audit filter facets (admin only) | `GET` | `/api/audit-logs/facets` |
| Run the read-only CRM Operations Agent | `POST` | `/api/operations-agent/runs` |
| Search/filter paginated Agent action proposals | `GET` | `/api/operations-agent/proposals` |
| Assign or unassign Agent proposals in bulk | `POST` | `/api/operations-agent/proposal-assignments` |
| Approve or reject an Agent proposal | `POST` | `/api/operations-agent/proposals/{proposal_id}/review` |

Writes require an `admin` or `advisor` role. Authenticated finance users can
read CRM data but cannot change it.

Audit history is read-only and restricted to `admin`. Queries support exact
entity type, entity ID, action, actor, date range, limit, and offset filters.
The API joins staff names for traceability and recursively replaces password,
token, secret, API-key, and authorization fields with `[REDACTED]` before data
reaches the browser.

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

The operations reminder scan turns trusted CRM state into internal action items:
tasks due within 24 hours, orders still awaiting payment after 24 hours, and
approved or booked trips departing within 14 days. A unique deduplication key
prevents repeated scans from creating duplicate reminders. Nothing contacts a
traveler automatically; an `admin` or `advisor` must acknowledge or dismiss each
item, and that decision is written to the audit trail.

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
AI_OPERATIONS_PROVIDER=gemini
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

## CRM Operations Agent

The Operations Copilot exposes four allowlisted, read-only functions: operational
counts, due tasks, pending-payment follow-ups, and upcoming departures. Gemini
3.8 Flash selects and composes these functions; it receives only the limited
business fields returned by those queries. The model cannot call write, payment,
booking, or communication functions.

Every run stores its provider, selected tools, result counts, and LangGraph trace
in `ai_runs`, with a credential-safe summary in the Audit Log. Unsafe external-
action claims fail validation. Availability degrades from Gemini 3.8 Flash to
Gemini 3.5 Flash Lite and then to the deterministic local LangGraph router, so an
LLM outage does not remove access to core operational data.

When a user explicitly asks to create a follow-up task for a pending-payment
order, the Agent stores a `pending` proposal instead of writing to CRM. An
`admin` or `advisor` must approve it. Approval rechecks that the source order is
still awaiting payment, prevents a second Agent-created task for the same order,
and atomically creates the task, marks the proposal `executed`, and writes Audit
Log entries. Each proposal expires after 24 hours; the API rechecks expiry at
review time and records blocked attempts as `expired`. Rejection requires a
reviewer reason and leaves task data unchanged. No proposal can execute a
payment, booking, order, or external communication.

The review queue accepts `status`, `assignment`, `search`, `limit`, and
`offset` query parameters. Search covers proposal titles, descriptions, and
order numbers; reviewers can filter work assigned to themselves or still
unassigned. Eligible pending proposals can be selected and assigned in bulk.
Expired or completed proposals are skipped, and every ownership change stores
before/after assignee IDs in the Audit Log. `expired` is calculated consistently
in the database query before filtering and pagination.

## AI Follow-up Copilot

An active reminder can generate one idempotent follow-up draft containing an
internal summary, recommended steps, and an editable traveler-message draft.
The local provider is deterministic. When `AI_FOLLOWUP_PROVIDER=gemini`—or when
that variable is omitted and `AI_PLANNING_PROVIDER=gemini`—the Copilot uses the
configured Gemini model with structured output.

The external context allowlist includes only member name, tier, locale, reminder
type, reason, severity, and recommended action. It excludes email, phone, full
payment records, and unrelated CRM notes. Every output is marked
`requires_human_review`; approving a draft only records that it is available to
the advisor and never sends email, SMS, or any other customer communication. If
the external model remains unavailable after retries, the workflow records a
clearly labelled local fallback draft so operations can continue safely.

## Communication approval workflow

An approved AI follow-up can become a separately versioned communication draft:

```text
AI output approved → editable communication draft → send approval → Mock Send
```

Editing either subject or body increments the version and resets any previous
send approval. The last editor cannot approve that version; approval is limited
to an `admin` account belonging to a different staff user. The UI records the
creator, last editor, approver, and sender by name. A `draft` cannot be sent
directly, and a `sent` record is immutable. Mock Send requires an
`Idempotency-Key`; replaying the same key returns the original result, while a
different key cannot send the same draft again. `MockEmailProvider` performs no
network request and stores only a local simulation receipt—it does not use a
real email address.

The built-in template catalog uses an explicit placeholder allowlist:
`member_name`, `reminder_title`, and `recommended_action`. Unknown or missing
fields fail closed instead of being silently rendered. Creating a draft,
manually editing it, or applying a template appends an immutable content
snapshot with its source, editor, and optional template version. Existing rows
from before this feature receive one migration snapshot of their current state;
earlier content cannot be reconstructed retroactively.

## AI regression evaluation

Run the deterministic baseline without external API calls:

```bash
python scripts/evaluate_ai.py --provider local --output output/ai-eval-local.json
```

The checked-in [`evals/baseline.local.json`](evals/baseline.local.json) records
the deterministic result: **12/12 cases passed**, with 100% schema, guardrail,
privacy, and explicit claim-safety checks. The fixtures cover three itinerary-
planning, three follow-up, and six Operations Agent scenarios. The Agent subset
also records 100% exact tool-selection accuracy on those six project-specific
prompts. This result verifies defined contracts only; it does not claim general
language understanding, subjective itinerary quality, real-time supplier
accuracy, or production-network performance.

Gemini evaluation is intentionally opt-in because it makes external requests:

```bash
python scripts/evaluate_ai.py --provider gemini --allow-live-api \
  --output output/ai-eval-gemini.json
```

## Background worker and retry queue

The `worker` service creates one idempotent reminder-scan job per configured time
bucket. MySQL `integration_events` is the durable job ledger; Redis Sorted Sets
hold only the execution schedule. On startup and during normal polling, the
worker recovers due `scheduled` or `retrying` jobs from MySQL, so a Redis restart
does not erase the source of truth.

Claimed jobs receive a processing lease. If a worker stops before completion,
the expired lease returns the job to `retrying` instead of leaving it stuck in
`processing` forever.

Failed jobs use capped exponential backoff. After `WORKER_MAX_ATTEMPTS`, a job
moves to `dead_letter` and requires an authenticated admin to reschedule it.
Worker executions use a null system actor in reminder audit entries instead of
impersonating a staff account.

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
migrations, and starts Redis, the FastAPI service, and the background worker. If Docker Hub is timing
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
workflow transitions. The reminder tests also verify rule output, deduplication
schema, API exposure, and terminal human-review states.

The current suite passes **70 automated tests**.

## Next milestone

1. Expand live-model evaluation and compare model/prompt versions
2. Add proposal SLA metrics and reviewer notifications
3. Production communication/payment adapters, monitoring, and secret management
