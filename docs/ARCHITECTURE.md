# VoyageOps AI Architecture

[繁體中文](ARCHITECTURE.zh-TW.md)

VoyageOps AI is an API-first travel CRM prototype. It demonstrates how a
backend system can add model-driven assistance without allowing a model to
silently mutate business data or perform external actions.

## Runtime components

```text
Browser Admin UI
       |
       v
FastAPI REST API -----> MySQL (system of record)
       |                    - CRM and trip data
       |                    - immutable quote snapshots
       |                    - AI runs and proposals
       |                    - audit and job ledgers
       |
       +--------------> Redis (scheduled-job wake-up index)
       |                         |
       |                         v
       |                  Background Worker
       |
       +--------------> Local/Gemini AI provider boundary
       |
       +--------------> MockPay / Mock Email adapters
                         (local-only, fail-closed)
```

MySQL is authoritative. Redis contains only recoverable scheduling metadata;
the worker can rebuild its runnable queue from the durable MySQL job ledger.

## Important request flows

### Quote to payment

```text
Itinerary -> immutable quote snapshot -> human approval -> idempotent order
          -> payment attempt -> signed/replay-safe webhook -> state transition
```

The repository includes a local MockPay adapter. It demonstrates the provider
contract, webhook authentication, idempotency, and audit flow, but it never
contacts a production payment processor.

### AI travel planning

```text
Travel request -> LangGraph workflow -> structured draft + guardrails
               -> human review -> editable itinerary
```

Only allowlisted fields are sent through the provider boundary. Model output is
validated against Pydantic schemas and cannot directly publish an itinerary.

### CRM Operations Agent

```text
User request -> intent routing -> read-only tools -> answer + trace
                                            |
                                            v
                                  optional write proposal
                                            |
                              assignment + SLA + human review
                                            |
                                  atomic task + audit write
```

The Agent's tools are read-only. A requested CRM write becomes a versioned,
expiring proposal. A qualified human reviewer must approve it before the
repository creates the task. Stale sources, expired proposals, and duplicate
execution are rejected.

### Operational reminders and communication

```text
Scheduled scan -> deduplicated reminder -> AI follow-up suggestion
               -> human-approved editable draft -> maker-checker approval
               -> idempotent local Mock Email receipt
```

Proposal SLA reminders join the same scheduler: pending proposals approaching
their deadline become high- or urgent-priority reminders, with stable
deduplication keys.

## Reliability and security boundaries

- Resource-oriented REST endpoints and explicit state machines reject invalid
  transitions with conflict responses.
- Idempotency keys protect order creation, payments, jobs, drafts, and sends.
- JWT authorization rechecks the staff user's current role and active state.
- Audit output recursively redacts credentials and secrets.
- Request middleware emits correlation IDs, processing time, structured logs,
  and bounded route-level Prometheus counters.
- `/health/live` verifies the process; `/health/ready` verifies MySQL and Redis.
- External payment and email actions are disabled by default and reported by
  `/api/operations/integrations/status`.

## Production boundary

This repository is a portfolio-grade local prototype, not a deployed production
travel platform. Production use still requires real provider adapters,
environment-specific secret management, infrastructure monitoring and alerts,
data-retention/privacy review, backups, and deployment hardening. These are
explicit boundaries rather than claimed implementation experience.
