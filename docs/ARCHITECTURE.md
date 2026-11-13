# Architecture

One FastAPI application renders Jinja templates and serves local CSS/JavaScript. PostgreSQL stores all durable state. HTTPX talks to official X APIs; the optional Anthropic adapter receives selected public evidence only. Fixture mode substitutes a persistent local synthetic provider and never invokes external providers.

## Boundaries

- Routes parse forms, require an operator session and CSRF, and call services.
- Discovery builds bounded queries, enriches authors from expansions, deduplicates and ranks.
- Evidence refresh updates source hashes and invalidates dependent approvals.
- Outreach services maintain one stable sender-recipient ledger and versioned exact-text approval.
- Sending checks current eligibility under PostgreSQL locks, commits an immutable attempt, then dispatches once outside the transaction.
- Synchronization imports conversation pages idempotently and derives attention from actual incoming events after the confirmed send.
- Usage reserves estimated costs under the workspace lock before external calls.

## Assisted outreach

The safety core (eligibility, approve, send, sync) is unchanged in behaviour. The assisted features call it.

- app/integrations/llm.py is the only place that calls a model. It picks the provider from DRAFT_PROVIDER, retries once on a fallback model when the first is busy, strips code fences, and writes one ai_calls row per request: purpose, provider, model, tokens, time, outcome and an application-authored error code. Provider response bodies are never stored or shown.
- app/services/fit.py judges the top 10 keyword matches of a search in one call. A judgment is kept only if it names a person from that search exactly once and every quote appears word for word in that person's stored posts. Strong and possible need at least one quote. Results are ordered strong, possible, unjudged, weak, then by keyword score.
- app/services/drafting.py asks the model for a message, validates its quotes the same way, and falls back to the template on any failure. draft_batch drafts the best matches of one search.
- app/services/queue.py holds the send queue. Approve and queue approves one exact version and stores a request key with it. A background thread wakes every QUEUE_TICK_SECONDS and, when nothing holds the queue, calls the existing send function for the oldest entry with that stored key. Because the key is stored before any dispatch, a restart replays the stored result instead of sending again. X refusing a message removes it from the queue; an unknown outcome stops the queue; a rate limit makes the queue wait.
- The same thread checks replies for sent messages every AUTO_SYNC_MINUTES for 14 days.
- eligibility() reads OUTREACH_POLICY. Under operator_approved it skips the allowlist and consent checks for evidence-based messages only. Test messages always need both.

Untrusted text: posts and profiles reach the model inside a JSON payload, never inside the instructions, and the instructions say to treat them as data. The model has no tools. Its output can only become a judgment or a draft, both checked against stored posts and both shown to a person before anything is sent.

Schema: migration 0002 adds the ai_calls table, AI fit columns on search_results and queue columns on outreach, and is safe to repeat.

## Transaction protocol

Lock workspace, sender account, outreach record, then attempt. All eligibility-changing service operations acquire the workspace lock, serializing them with send reservation. The network operation occurs only after the reservation commits. A process interruption retains the reservation; startup/activity recovery changes a stale in-flight attempt to unknown, never to ready-to-send.

Token rotation uses a short claim transaction, a network exchange outside the transaction, and a second guarded persistence transaction. Simultaneous refresh attempts see TOKEN_REFRESH_BUSY. An interrupted refresh requires reconnection because the provider may already have rotated the token.

Positive reconciliation requires one matching outgoing event in the correct conversation and dispatch time window. Absence or ambiguity leaves the hold intact. Independent sends from another tool are outside the installation's guarantee.

## State

Preparation version, send status, reply state and eligibility are separate. Approval contains the draft hash/version, identities, selected source hashes, purpose version and consent version. Editing/regeneration or source/consent/purpose changes invalidate it. Reconnecting the same account retains its X ID and history.

The unique outreach constraint is sender X ID plus recipient X ID inside a database whose mode is immutable. This is equivalent to mode/workspace/sender/recipient identity for the single-workspace installation; mode and workspace cannot be switched within that database.

DM event uniqueness is account ID plus external event ID. Sync commits received pages before continuing. Partial failure preserves stored pages but never reports a complete sync.

## Security

Argon2 password hashing, expiring random server-side sessions, HttpOnly/SameSite cookies, origin/CSRF checks, PKCE/state, and authenticated token encryption protect the operator flow. The deployment key is external to PostgreSQL. No credentials or provider error bodies are placed in user-visible diagnostics. Uvicorn access logs must remain disabled to avoid callback query logging.

The interface keeps evidence and draft side by side. Unsaved text edits disable approval/send buttons, while the server remains authoritative. This UI arrangement follows the frontend design guidance to make review, rather than decorative dashboard metrics, the main action.

## Official contracts

Reviewed 2026-11-12:

- https://docs.x.com/x-api/direct-messages/manage/integrate
- https://docs.x.com/x-api/direct-messages/lookup/quickstart
- https://docs.x.com/x-api/posts/search-recent-posts
- https://help.x.com/en/rules-and-policies/x-automation
- https://platform.claude.com/docs/en/api/messages/create
- https://ai.google.dev/api/generate-content (Gemini generateContent; called for real on 2026-11-14)
- https://www.postgresql.org/docs/current/explicit-locking.html

Actual account access remains a separate live-verification requirement.
