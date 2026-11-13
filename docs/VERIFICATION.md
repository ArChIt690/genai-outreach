# Verification

Checked on 2026-11-12 using Python 3.12.14, PostgreSQL 17.11, and Microsoft Edge controlled through Playwright. The native database was started on loopback in the development workspace without installing a service. Fixture data is synthetic.

Re-checked on 2026-11-14 after the assisted-outreach work, using Python 3.12.12, PostgreSQL 18.6 and Microsoft Edge through Playwright, against a throwaway local database.

## Automated results

- 173 tests passed, including two browser workflows. 65 of them existed before the assisted-outreach work and pass unchanged.
- Ruff checks passed.
- Python compilation passed.
- pip check reported no broken requirements.
- One deprecation warning remains in the installed Starlette/HTTPX test-client integration; it did not fail any test.

Tests include two separate database sessions racing to send, accepted-then-timeout reconciliation, uncertain/ambiguous history, request replay, restart recovery, consent/purpose changes, suppression, partial page imports, opt-outs, OAuth state consumption and refresh coordination. HTTPX mocks verify actual endpoint paths and request parameters without calling X.

The browser test signs in, performs discovery, generates and approves a source-based draft, checks that unconsented sending is disabled, registers a controlled synthetic recipient, saves/approves a test message, sends through the canonical fixture provider, adds and syncs a reply, and checks the activity table. A 390-pixel viewport has no horizontal overflow or JavaScript page errors. Desktop, evidence review, conversation and mobile screenshots are under screenshots/.

The assisted-outreach tests add: the send rule under both policies; the Gemini adapter against a mocked server, including the busy-model fallback, fenced JSON, an empty answer and the daily call limit; invented, borrowed and missing quotes in judging and drafting; queue pacing, the daily limit, holds, a refusal by X, an unknown outcome, and a restart between dispatch and queue clean-up; automatic and one-click reply checks; CSRF on every new action; and that the packaging script refuses a template that still holds a secret.

The second browser test signs in, searches, checks the AI fit and reason on a card, batch drafts, edits and saves one draft, approves both, lets the queue send them, syncs replies and opens the AI usage panel. Model answers in that test are canned; no network call is made.

## Real Gemini run (2026-11-14)

One run in fixture mode with a real Gemini key, OUTREACH_POLICY=operator_approved, a real browser and the real background worker. X data was synthetic.

- Both migrations ran through Alembic on a new empty database.
- Search plus AI judging of three people took 7.9 seconds. Ada and Mira were judged strong, the news account weak and "not a person". Every quote passed the word-for-word check.
- Batch drafting made two drafts in 11.7 seconds. Each named something the person had posted (for example the released evaluation scripts for a manipulation benchmark), was under 500 characters and ended with a STOP line. Neither needed the template fallback.
- After Approve and queue, the worker sent both messages with no further clicks, 4.1 seconds apart with the gap set to 4 seconds for the run.
- A synthetic reply was added and Sync all now moved that conversation to Needs attention.
- The AI usage panel listed the three calls: 929, 511 and 536 tokens, 5 to 8 seconds each, all answered by gemini-2.5-flash.
- An earlier attempt the same day with gemini-flash-latest as first model timed out on every call and was answered by the fallback model after 30 seconds. The defaults were changed because of that.

Screenshots from this run: screenshots/review-gemini.png and screenshots/ai-usage-gemini.png.

## Capability status

| Capability | Status | Qualification |
| --- | --- | --- |
| Database transactions and concurrency | fixture_verified | Real PostgreSQL, synthetic provider |
| Operator sessions and CSRF | fixture_verified | HTTP and real browser tests |
| OAuth state/PKCE implementation | fixture_verified | State/expiry/replay and contract tests; no actual user grant |
| Token refresh coordination | fixture_verified | Two callers, one mocked rotation |
| Public discovery and ranking | fixture_verified | Synthetic posts; real endpoint request contract tested |
| Evidence revalidation and approval invalidation | fixture_verified | Deleted/changed source tests |
| Personalized template drafting | fixture_verified | Evidence-attributed draft visible in browser |
| Optional Anthropic adapter | implemented | Mocked failure/source checks; no live model account |
| Gemini adapter, fallback model, call log | model_verified | Real Gemini calls on synthetic posts; mocked failure paths |
| AI fit judging with quote checks | model_verified | Real Gemini on synthetic posts; invented-quote tests |
| AI drafting and batch drafting | model_verified | Real Gemini on synthetic posts; fallback tests |
| Send rule (OUTREACH_POLICY) | fixture_verified | Both policies tested; never run on real X |
| Review queue | fixture_verified | HTTP tests and real browser |
| Paced send queue and worker | fixture_verified | Service tests; real worker thread in the Gemini run |
| Scheduled and one-click reply checks | fixture_verified | Service tests and real browser |
| AI usage panel | model_verified | Shows the real calls from the Gemini run |
| Migration 0002 | fixture_verified | Alembic on an empty database; repeat-run test |
| Approval, consent, suppression | fixture_verified | Server-side tests plus browser flow |
| Initial sending | fixture_verified | Canonical send service; no external dispatch |
| Reply sync and attention | fixture_verified | Pagination/failure/idempotency tests and browser |
| Fresh locked dependency setup | fixture_verified | Isolated new virtual environment and database |
| Compose configuration | implemented | CLI configuration validation passed with no secret resolution |
| Docker image build and containers | not_run | Docker Engine was not running |
| Actual X authorization | blocked | Credentials not provided in this workspace |
| Actual X discovery | blocked | Requires connected live account |
| Actual X send and received reply | blocked | Requires human-operated controlled live test |
| Final recorded demonstration | not_run | Candidate must record actual behavior |

## Clean setup trial

A fresh virtual environment installed the exact lock file from locally cached wheels, passed dependency checking, migrated a new dedicated PostgreSQL database, reran the migration idempotently, and served readiness/sign-in through the application. Elapsed time was 32.0 seconds.

This trial excludes wheel downloads, Docker image acquisition, developer-account approval and account credentials. A cold Docker/evaluator setup must still be timed before promising their complete setup duration.

## Remaining live acceptance steps

1. Provision a separate live-mode database and configure the OAuth client and numeric test-recipient allowlist locally.
2. Connect the sender in Settings and verify the exact returned identity/scopes.
3. Run a bounded real public search and inspect the resulting source links.
4. Verify the actual selected conversation read. Resolve any entitlement/encryption restriction without bypassing it.
5. Record valid test consent, review historical uncertainty, and approve the exact test message.
6. The human operator enables live test sending in configuration and presses Send once in the app.
7. Confirm the actual message in the controlled recipient account; reply and sync it.
8. Update this report with dated real outcomes. Keep IDs/private text out of public materials where unnecessary.
9. Record the required demonstration without clearing the sender-recipient ledger.
10. Only after the steps above, decide whether to set OUTREACH_POLICY=operator_approved, and check the queue's pace and daily limit against the account's real DM limits.

Until those steps succeed, this is implemented and fixture-verified software with pending live acceptance, not a fully verified completion of the assignment.
