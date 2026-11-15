# Verification

Checked on 2026-11-12 using Python 3.12.14, PostgreSQL 17.11, and Microsoft Edge controlled through Playwright. The native database was started on loopback in the development workspace without installing a service. Fixture data is synthetic.

Re-checked on 2026-11-14 after the assisted-outreach work, using Python 3.12.12, PostgreSQL 18.6 and Microsoft Edge through Playwright, against a throwaway local database.

## Automated results

- 230 tests passed, including two browser workflows. 65 of them existed before the assisted-outreach work and pass unchanged.
- Tests remove real credentials from the environment before they run, so a developer's own keys can never be used or printed by a test.
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

## Live test on real X and OpenAI (2026-11-15)

One controlled end-to-end run in live mode. The sender was the candidate's own X account; the only recipient was a second X account the candidate also controls, registered as a test recipient with recorded consent. OUTREACH_POLICY was test_allowlist, so no other account could have been messaged. AUTO_SYNC_MINUTES was 0.

| Step | Result |
| --- | --- |
| Connect the sender with OAuth 2.0 (PKCE) | Worked; the account showed as authorized |
| Profile lookup of the recipient | Worked |
| Register test consent | Worked; registered again after the sender name and purpose changed, as designed |
| Topic search on a rare phrase posted by the recipient | Worked; one post and one person returned, scored 6/10 |
| AI fit judging with OpenAI gpt-6-luna | Worked after a key fix (below): strong / builder, reason and a word-for-word quote. 442 tokens in, 108 out, 4.8 s |
| AI draft with gpt-6-luna | Worked; named the post, the sender and the purpose, ended with the STOP line |
| Approve and queue | The background worker sent the DM 20 seconds after approval; X returned a message ID |
| Delivery | The DM arrived in the recipient's message requests (the accounts did not follow each other at send time) |
| Reply and sync | The recipient replied; a sync stored both messages and the conversation moved to Needs attention |

Spend: about USD 0.18 of X by the app's estimate (including two repeated searches while fixing the key) and well under one cent of OpenAI.

Two problems found and fixed during the run:

- The first two OpenAI calls returned HTTP 401. An older OPENAI_API_KEY in the Windows user environment was overriding the one in .env (environment variables take precedence). Removing the Windows variable and restarting fixed it. The app handled the failure as designed: it logged the code and fell back to keyword ranking.
- The DM was first missed because X now shows direct messages under Chat, and messages from accounts the recipient does not follow land in Requests.

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
| OpenAI adapter and Rewrite | live_verified (luna) | Real fit judging and drafting with gpt-6-luna; Rewrite with gpt-6.1-terra mocked only |
| Seed accounts (similar people) | fixture_verified | Mocked model and synthetic X; unsafe topics, unknown and empty seeds tested. No real X or model call |
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
| Docker image build and containers | fixture_verified | 2026-11-15: clean copy, built and started in about 75 s; sign-in, search, batch draft, queue and send worked in fixture mode |
| Actual X authorization | live_verified | OAuth 2.0 with PKCE on 2026-11-15 |
| Actual X discovery | live_verified | One rare-phrase search on 2026-11-15 |
| Actual X send and received reply | live_verified | One DM to a controlled account, reply synced, 2026-11-15 |
| OpenAI fit judging and drafting | live_verified | gpt-6-luna on 2026-11-15. gpt-6.1-terra (backup and Rewrite) not exercised |
| Final recorded demonstration | not_run | Candidate must record actual behavior |

## Clean setup trial

A fresh virtual environment installed the exact lock file from locally cached wheels, passed dependency checking, migrated a new dedicated PostgreSQL database, reran the migration idempotently, and served readiness/sign-in through the application. Elapsed time was 32.0 seconds.

On 2026-11-15 both README setup paths were repeated from a clean copy of the repository (fixture mode, no X or AI calls):

- Docker: `docker compose run --rm setup` created `.env` and the password hash inside Docker (no Python on the host), then `docker compose up` started the app in about 5 seconds and sign-in with that password worked. In the earlier trial `docker compose up --build` built and started the app and database in about 75 seconds; migrations ran automatically; sign-in, a search, batch drafting, approve and queue, the automatic send (after ticking the history box) and reply sync all worked. Publishing the database port was removed from compose.yaml because it clashed with a local PostgreSQL.
- Docker Hub: the image was published as archit690/genai-outreach (linux/amd64 and linux/arm64, about 140 MB to download) from a clean copy of the committed code, after scanning every file in it for keys, password hashes, .env files and notes (none found). From a clean folder with no local image, `docker compose run --rm setup` downloaded it instead of building, and `docker compose up`, sign-in and a synthetic search worked.
- Without Docker: a plain `pip install -r requirements.lock` into a new environment took 83 seconds; `alembic upgrade head` created all tables on an empty database; the app started, sign-in and a synthetic search worked.

Neither trial includes creating an X developer app, its approval or buying credits; those depend on X.

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

Steps 1 to 8 were completed once on 2026-11-15 (see Live test above). Step 10 remains: the send rule stayed test_allowlist, and the queue's pace and daily limit have not been checked against the account's real DM limits.
