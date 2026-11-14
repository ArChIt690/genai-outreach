# Implementation status

Last updated 2026-11-14. Statuses: verified on synthetic data (fixture), verified with a real model, or not yet run for real.

| Part | Status | Evidence |
| --- | --- | --- |
| App, database schema, three migrations | Fixture verified | Fresh-database Alembic run; repeat-run tests |
| Sign-in, sessions, CSRF | Fixture verified | HTTP and browser tests |
| X adapters: OAuth, search, profile, DM read and send | Written; not run against real X | Mocked contract tests only; no developer credentials were available |
| Topic search and keyword scoring | Fixture verified | Service tests on synthetic posts |
| Seed accounts (similar people) | Fixture verified | Mocked model; unsafe-topic, unknown-seed and empty-seed tests |
| AI fit judging with quote checks | Verified with real Gemini on synthetic posts | Real run on 2026-11-14; invented-quote tests |
| AI drafting, batch drafting | Verified with real Gemini on synthetic posts | Real run on 2026-11-14; fallback tests |
| OpenAI provider and Rewrite | Written; not run against the real API | Mocked server tests: success, fallback, cut-off answer, refusal, wrong key |
| Anthropic provider | Written; not run | Mocked failure tests |
| Send rule (OUTREACH_POLICY) | Fixture verified | Both policies tested |
| Review page, send queue, background worker | Fixture verified | Service, HTTP and browser tests; real worker thread in the Gemini run |
| Duplicate prevention, no-retry, recovery | Fixture verified | Real PostgreSQL race, timeout, replay and restart tests |
| Reply checks, STOP handling | Fixture verified | Service and browser tests |
| AI usage panel | Verified with real Gemini | Shows the real calls from the run |
| Packaging | Verified | Refuses a template that holds a secret; leaves out .env and working notes |
| Docker setup | Not run | Docker was not running on the development machine |
| Live X authorization, search, send, reply | Not run | Needs a developer app, credits and a controlled recipient |
| Demo recording | Not done | To be recorded by the candidate |

230 automated tests pass, including two browser workflows. Lint and dependency checks pass.

No real X request, real message, or OpenAI call has been made. The only external service called was Google Gemini, on synthetic posts.
