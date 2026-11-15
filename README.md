# GenAI Fund outreach prototype

A Python workbench for outreach on X to people building in AI and robotics. It finds people from recent public posts, has an AI model judge fit and draft a personal message from their own posts, puts every draft in a review queue for a person to approve, sends approved messages at a safe pace, and tracks replies.

AI does the reading and writing. A person approves every message. Nothing is sent without that approval.

Verified: the whole flow on synthetic X data (fixture mode), including real Google Gemini calls for fit judging and drafting. Not verified: anything against the real X API, because no X developer credentials were available. This is an assessment prototype, not a finished campaign platform.

## Requirements

- Python 3.12 or compatible supported Python.
- PostgreSQL 17, or Docker Desktop/Engine with Compose.
- For live mode: an approved X developer app, OAuth client ID/secret, API credits and DM permissions, and a controlled/explicitly consenting recipient.
- Optional: an OpenAI or Google Gemini API key for AI fit judging and drafting. Without one the app ranks by keywords and writes a template draft.

## Start with Docker

Run from this directory. Python is used once to generate local secrets and choose your password.

    python -m venv .venv
    .venv\Scripts\python.exe -m pip install -r requirements.lock
    .venv\Scripts\python.exe -m scripts.bootstrap --fixture-demo
    docker compose up --build

On macOS/Linux use .venv/bin/python in place of .venv\Scripts\python.exe.

Open http://127.0.0.1:8000 and sign in with the password you chose. The app and database listen only on loopback through this development configuration. Do not expose this Compose file publicly. If port 5432 is occupied, change the DB port mapping; the container-to-container address is unchanged.

The bootstrap script refuses to overwrite an existing .env. To change your operator password while retaining credentials, run:

    python -m scripts.bootstrap --reset-password

Restart the app after configuration changes. Never commit .env, a real database dump, private messages or credentials.

## Start against an existing PostgreSQL database

Create a dedicated empty database and use its connection URL:

    python -m scripts.bootstrap --fixture-demo --database-url "postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/outreach"
    python -m alembic upgrade head
    python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log

Keep the terminal's working directory at the project root. The commands assume the virtual environment is active or its Python executable is used explicitly. Access logs are disabled so OAuth callback codes do not enter request logs.

## Fixture walkthrough

Fixture mode uses only synthetic profiles, source posts and conversations. It makes no X calls. If DRAFT_PROVIDER=gemini is set, the synthetic posts are sent to Gemini for judging and drafting.

### Assisted flow: search, review, queue

Set these in .env and restart (the AI lines are optional; use gemini and GEMINI_API_KEY for Gemini):

    OUTREACH_POLICY=operator_approved
    DRAFT_PROVIDER=openai
    OPENAI_API_KEY=your-key

1. Sign in and search for robotics, embodied AI. Each person shows a fit (strong, possible or weak), a reason, and the quotes behind it.
2. Select Draft for top matches. The app drafts a message for every strong or possible match, up to 10, and opens Review.
3. On each Review card, read the reason, the quotes and the source posts. Edit the text if needed. Then choose Approve and queue, Skip, or Do not contact. Approving covers exactly the text on screen. If you do not like a draft, type an optional note such as "shorter" and select Rewrite: the stronger model writes a new draft from the same posts.
4. Approved messages wait in the send queue. The app sends them one at a time, SEND_MIN_GAP_SECONDS apart, up to DAILY_SEND_LIMIT per day. Activity shows each message's place in the queue and the reason for any hold.
5. Open a sent person's page, add a fixture reply, then select Sync all now in Activity. The conversation moves to Needs attention.

### Start from seed accounts

Instead of topics, enter one to three X handles you already rate under "Or start from accounts you already rate" and select Find similar people. The AI reads each seed's public bio and up to five recent posts, writes one sentence describing their work, and proposes search topics. The app runs its normal search with those topics, leaves the seeds out of the results, and judges each person by how similar their work is to the seeds. The results page shows the seeds, the AI's description and the topics used.

This needs an AI provider. It finds people who do similar work; it does not read who the seeds follow or talk to.

### Manual test-recipient flow

1. Sign in. Search for robotics and embodied AI.
2. Open a candidate, prepare a message and draft from evidence. Inspect source text and approve the current version. Sending stays blocked without contact permission.
3. In Settings, save your sender details and acknowledge the limited history window.
4. Register handle test_recipient. Use a synthetic test-consent reference and check the controlled-account confirmation.
5. Open that recipient, prepare a message, write a short test message and select the manually written test-message checkbox.
6. Save, approve the exact version, and simulate the approved send.
7. Add a fixture reply, then select Sync replies. Review Needs attention and mark the reply handled.
8. A second initial send is blocked. Do not clear real history to repeat a live demonstration.

Fixture content and live data must use separate databases. The app refuses to start when APP_MODE disagrees with the database's stored mode.

## Who can be messaged

One setting, OUTREACH_POLICY, decides this. Settings and the top bar show which value is active.

| Value | Who can be messaged |
| --- | --- |
| test_allowlist (default) | Only accounts listed in TEST_RECIPIENT_IDS that have recorded test consent. Use this to test the tool. |
| operator_approved | Any discovered person, once a person has approved the exact text. The allowlist and consent checks are skipped for evidence-based messages. |

Under both values the app still enforces: human approval of the exact text, the do-not-contact list, one initial message per person, the pause switch, SEND_ENABLED, the daily limit, the X budget, and a fresh re-read of the quoted posts. A reply of STOP adds the person to the do-not-contact list.

Switch to operator_approved on real X only for outreach your organisation has decided to run from its own account. To test this tool, keep test_allowlist and message accounts you control or people who agreed to the test.

## AI fit judging and drafting

Choose one provider in .env:

- OpenAI: DRAFT_PROVIDER=openai and OPENAI_API_KEY. OPENAI_MODEL (default gpt-6-luna) does the judging and drafting. OPENAI_STRONG_MODEL (default gpt-6.1-terra) is tried when the first model is busy, and writes every Rewrite.
- Gemini: DRAFT_PROVIDER=gemini and GEMINI_API_KEY. Defaults: GEMINI_MODEL=gemini-2.5-flash, GEMINI_FALLBACK_MODEL=gemini-flash-lite-latest. Gemini has no separate stronger model, so Rewrite uses the same one.

The OpenAI adapter is tested against a mocked server only; it has not yet been run against the real API. The Gemini adapter has.

- After each search, one model call judges the top 10 keyword matches. For each person it returns a fit, a role, a short reason and the quotes the reason rests on.
- The app checks every quote word for word against that person's stored posts. If any quote is not found, that person's AI judgment is thrown away and the keyword score stands alone. There is no confidence percentage.
- A draft must be at most 500 characters, cite quotes that pass the same check, and contain a STOP opt-out line. Otherwise the app uses the template draft and labels it as a fallback.
- If the first model is busy or rate limited, the call is tried once on the fallback model. If that fails too, the app falls back to keyword ranking or the template and says so on screen.
- Only public profile text, public posts, the sender name and the purpose are sent to the model. DMs and tokens never are. Posts are passed as data and the instructions tell the model to treat them as untrusted.
- Settings has an AI usage section: every call with its model, tokens, time and result. AI_DAILY_CALL_LIMIT (default 200) caps calls per UTC day.

Google's free tier may use submitted content to improve its products. What this app submits is public posts plus your sender name and purpose. Use a paid key if that matters to you. For OpenAI, check the data controls of your own account.

## Settings for assisted outreach

| Setting | Default | Meaning |
| --- | --- | --- |
| OUTREACH_POLICY | test_allowlist | Who can be messaged. See above. |
| DRAFT_PROVIDER | template | template, openai, gemini or anthropic. |
| OPENAI_API_KEY | empty | Needed for openai. Keep it in .env only. |
| OPENAI_MODEL / OPENAI_STRONG_MODEL | gpt-6-luna / gpt-6.1-terra | Everyday model; backup and Rewrite model. |
| GEMINI_API_KEY | empty | Needed for gemini. Keep it in .env only. |
| GEMINI_MODEL / GEMINI_FALLBACK_MODEL | gemini-2.5-flash / gemini-flash-lite-latest | First model and the one tried when the first is busy. |
| AI_DAILY_CALL_LIMIT | 200 | Model calls per UTC day. |
| DRAFT_LIMIT_PER_SESSION | 40 | Drafts per sign-in. |
| DAILY_SEND_LIMIT | 10 | Send attempts per UTC day. This is our caution, not an X quota. |
| SEND_MIN_GAP_SECONDS | 120 | Minimum gap between queued sends. |
| QUEUE_TICK_SECONDS | 30 | How often the background worker wakes. |
| AUTO_SYNC_MINUTES | 180 | Minutes between automatic reply checks, for 14 days after a send. 0 turns it off. See docs/COSTS.md before lowering it. |
| WORKER_ENABLED | true | Set false to stop automatic sending and reply checks. |

Run exactly one app process. The send queue and reply checks run inside it and stop when it stops; they continue from the database when it starts again.

## Connect a real X account

Provision a new, separate database for live mode. Edit your local .env:

    APP_MODE=live
    DATABASE_URL=postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/outreach_live
    APP_ORIGIN=http://127.0.0.1:8000
    X_CALLBACK_URL=http://127.0.0.1:8000/oauth/x/callback
    X_CLIENT_ID=your-client-id
    X_CLIENT_SECRET=your-confidential-client-secret
    TEST_RECIPIENT_IDS=the-consenting-recipient-numeric-x-id
    SEND_ENABLED=false

Keep your generated encryption key and password hash. Register the exact callback URI in the X developer console, enable user authentication, and grant tweet.read, users.read, dm.read, dm.write and offline.access. Run migrations, restart, and use Connect with X in Settings.

First verify identity, real discovery and a tracked conversation read. Record the outcome in docs/VERIFICATION.md. Account access does not prove recipient compatibility: encryption, entitlement or recipient settings may block the standard DM endpoint.

To perform a single live test, record explicit test consent for the allowlisted recipient, acknowledge history limits, set SEND_ENABLED=true locally and restart. The human operator must inspect and approve the exact message, then press Send approved message. No setup script or automated test sends it for you.

An incoming consent message before the initial send does not count as a reply. Available history is checked for outgoing prior contact, but the API's thirty-day window cannot prove absence of older messages. Use a previously uncontacted controlled test pair. Ordinary conversation continuation happens in X, not through automated follow-ups here.

## Template and Anthropic drafting

The default DRAFT_PROVIDER=template attributes a selected public post directly and incorporates your supplied purpose. It is labeled as a template.

The optional Anthropic Messages adapter is implemented but has not been verified against a real model account. To enable it in live mode, set DRAFT_PROVIDER=anthropic, ANTHROPIC_API_KEY, ANTHROPIC_MODEL and MODEL_DATA_USE_ACKNOWLEDGED=true only after reviewing X/provider processing terms and your provider's retention settings. Private DM content and OAuth tokens never enter the model request.

Model schema/source validation cannot establish semantic truth. Review every claim. Invalid/unavailable model output falls back visibly to the evidence template. A conservative USD 0.10 allowance is reserved per model call; configure provider spending controls and verify that the selected model/request size fits that reservation.

## Tests

Use a disposable PostgreSQL database whose name starts with outreach_test. Tests truncate only that explicitly selected test database. Never point tests at a live workspace.

PowerShell:

    $env:TEST_DATABASE_URL="postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/outreach_test"
    python -m pytest -q
    python -m ruff check .
    python -m pip check

Browser tests use installed Microsoft Edge on Windows. Else install Playwright Chromium with python -m playwright install chromium, or set BROWSER_EXECUTABLE to an existing compatible browser. For service tests alone, run python -m pytest -m "not browser" -q.

The suite also covers the send rule in both policies, the Gemini adapter against a mocked server (including the busy-model fallback), rejection of invented quotes in judging and drafting, queue pacing, the daily limit, restart safety, stop-on-unknown, automatic reply checks, and a second browser test of the assisted flow. It covers database concurrency, approval invalidation, consent, request replay, accepted-then-timeout, uncertain reconciliation, pagination/partial sync, opt-outs, OAuth state, refresh rotation, CSRF and the complete synthetic browser workflow. Screenshots are saved under docs/screenshots.

## Maintenance

    python -m scripts.maintenance refresh
    python -m scripts.maintenance expire --days 30

Refresh selected sources regularly and promptly handle deletion/privacy requests. Settings provides a local content purge and token disconnect. Neither action deletes messages from X. Minimal identity/contact metadata is retained for duplicate prevention. See docs/KNOWN_LIMITATIONS.md for full removal.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| Connection refused | Start PostgreSQL; check DATABASE_URL and port. |
| Missing tables | Run python -m alembic upgrade head. |
| MODE_MISMATCH | Choose a separate database for the requested mode. |
| SENDING_DISABLED | Intentionally enable only controlled tests in deployment configuration and restart. |
| CONSENT_REQUIRED | Record valid consent for this sender, recipient and current purpose. |
| AI calls fail with HTTP_401 | The provider refused the key. An OPENAI_API_KEY or GEMINI_API_KEY set in the operating system environment overrides .env; remove it or make it match, then restart the app from a new terminal. |
| Sent DM not visible to the recipient | X shows DMs under Chat. Messages from accounts the recipient does not follow arrive under Requests. |
| RECIPIENT_NOT_ALLOWED | Under test_allowlist only registered test recipients can be messaged. See Who can be messaged. |
| Queue shows Holding | The note names the reason: pacing and daily limit clear by themselves; sending disabled, paused, sender busy or account reconnect need action in Settings or Activity. |
| AI fit judging was unavailable | Both Gemini models failed or the daily call limit was reached. Results use keyword ranking. Check Settings, AI usage. |
| Draft labelled as a fallback | The model failed, cited a quote that is not in the posts, wrote over 500 characters or left out the STOP line. The template was used instead. |
| APPROVAL_STALE | Save the current text, inspect the evidence and approve again. |
| ALREADY_CONTACTED | Use existing activity; do not erase the ledger to send again. |
| SEND_UNKNOWN | Inspect/reconcile. No-match does not authorize resending. |
| HISTORY_INCOMPLETE | Resolve API permission/rate/pagination issues before sending. |
| X_PERMISSION_OR_RECIPIENT_RESTRICTED | Check DM permissions, recipient settings, account/encryption requirements. |
| BUDGET_EXCEEDED | Review local estimates and provider billing before changing the allowance. |
| Dependency downloads stall on wheel metadata | This host required pip's legacy resolver; using --use-deprecated=legacy-resolver completed installation. Pinned offline-wheel installation was also tested. |

See docs/ARCHITECTURE.md, docs/VERIFICATION.md and docs/DEMO_SCRIPT.md before recording a submission. The current delivery contains a demo script and synthetic screenshots, not a fabricated live demo video.
