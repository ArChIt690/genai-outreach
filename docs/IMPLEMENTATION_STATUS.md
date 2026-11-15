# Implementation status

Last updated 2026-11-15. Statuses: verified on synthetic data (fixture), verified with a real model, or not yet run for real.

| Part | Status | Evidence |
| --- | --- | --- |
| App, database schema, three migrations | Fixture verified | Fresh-database Alembic run; repeat-run tests |
| Sign-in, sessions, CSRF | Fixture verified | HTTP and browser tests |
| X adapters: OAuth, search, profile, DM read and send | Verified on real X | One controlled live test on 2026-11-15: connect, search, send, reply sync |
| Topic search and keyword scoring | Fixture verified | Service tests on synthetic posts |
| Seed accounts (similar people) | Fixture verified | Mocked model; unsafe-topic, unknown-seed and empty-seed tests |
| AI fit judging with quote checks | Verified with real Gemini on synthetic posts | Real run on 2026-11-14; invented-quote tests |
| AI drafting, batch drafting | Verified with real Gemini on synthetic posts | Real run on 2026-11-14; fallback tests |
| OpenAI provider | Verified with real gpt-6-luna | Fit judging and a draft in the live test; Rewrite (gpt-6.1-terra) mocked only |
| Anthropic provider | Written; not run | Mocked failure tests |
| Send rule (OUTREACH_POLICY) | Fixture verified | Both policies tested |
| Review page, send queue, background worker | Fixture verified | Service, HTTP and browser tests; real worker thread in the Gemini run |
| Duplicate prevention, no-retry, recovery | Fixture verified | Real PostgreSQL race, timeout, replay and restart tests |
| Reply checks, STOP handling | Fixture verified | Service and browser tests |
| AI usage panel | Verified with real Gemini | Shows the real calls from the run |
| Packaging | Verified | Refuses a template that holds a secret; leaves out .env and working notes |
| Docker setup | Fixture verified | Clean-copy build and start in about 75 s on 2026-11-15; full fixture flow worked |
| Live X authorization, search, send, reply | Verified once | Sender and recipient both controlled by the candidate; about USD 0.18 of X |
| Operator-approved sending on real X | Not run | The live test kept the test-list-only rule |
| Demo recording | Not done | To be recorded by the candidate |

251 automated tests pass, including two browser workflows. Lint and dependency checks pass.

Real services used: Google Gemini on synthetic posts (2026-11-14); X and OpenAI gpt-6-luna in one controlled live test (2026-11-15).
