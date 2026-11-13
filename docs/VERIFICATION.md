# Verification

Checked on 2026-11-12 using Python 3.12.14, PostgreSQL 17.11, and Microsoft Edge controlled through Playwright. The native database was started on loopback in the development workspace without installing a service. Fixture data is synthetic.

## Automated results

- 65 tests passed, including the browser workflow.
- Ruff checks passed.
- Python compilation passed.
- pip check reported no broken requirements.
- One deprecation warning remains in the installed Starlette/HTTPX test-client integration; it did not fail any test.

Tests include two separate database sessions racing to send, accepted-then-timeout reconciliation, uncertain/ambiguous history, request replay, restart recovery, consent/purpose changes, suppression, partial page imports, opt-outs, OAuth state consumption and refresh coordination. HTTPX mocks verify actual endpoint paths and request parameters without calling X.

The browser test signs in, performs discovery, generates and approves a source-based draft, checks that unconsented sending is disabled, registers a controlled synthetic recipient, saves/approves a test message, sends through the canonical fixture provider, adds and syncs a reply, and checks the activity table. A 390-pixel viewport has no horizontal overflow or JavaScript page errors. Desktop, evidence review, conversation and mobile screenshots are under screenshots/.

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

Until those steps succeed, this is implemented and fixture-verified software with pending live acceptance, not a fully verified completion of the assignment.
