# GenAI Fund outreach prototype

A Python workbench for finding relevant public AI/robotics work on X, reviewing the evidence, composing an exact message, recording human approval, and tracking a consented test conversation.

The fixture workflow is implemented and tested. Live X account access and real sending have not been verified in this workspace because credentials were not supplied. This is an assessment prototype, not a finished campaign platform.

## Requirements

- Python 3.12 or compatible supported Python.
- PostgreSQL 17, or Docker Desktop/Engine with Compose.
- For live mode: an approved X developer app, OAuth client ID/secret, API credits and DM permissions, and a controlled/explicitly consenting recipient.
- No LLM credential is required for evidence-template drafts.

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

Fixture mode uses only synthetic profiles, source posts and conversations; it makes no X/model calls.

1. Sign in. Search for robotics and embodied AI.
2. Open a candidate, prepare a message and draft from evidence. Inspect source text and approve the current version. Sending stays blocked without contact permission.
3. In Settings, save your sender details and acknowledge the limited history window.
4. Register handle test_recipient. Use a synthetic test-consent reference and check the controlled-account confirmation.
5. Open that recipient, prepare a message, write a short test message and select the manually written test-message checkbox.
6. Save, approve the exact version, and simulate the approved send.
7. Add a fixture reply, then select Sync replies. Review Needs attention and mark the reply handled.
8. A second initial send is blocked. Do not clear real history to repeat a live demonstration.

Fixture content and live data must use separate databases. The app refuses to start when APP_MODE disagrees with the database's stored mode.

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

## Optional model drafting

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

The suite covers database concurrency, approval invalidation, consent, request replay, accepted-then-timeout, uncertain reconciliation, pagination/partial sync, opt-outs, OAuth state, refresh rotation, CSRF and the complete synthetic browser workflow. Screenshots are saved under docs/screenshots.

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
| APPROVAL_STALE | Save the current text, inspect the evidence and approve again. |
| ALREADY_CONTACTED | Use existing activity; do not erase the ledger to send again. |
| SEND_UNKNOWN | Inspect/reconcile. No-match does not authorize resending. |
| HISTORY_INCOMPLETE | Resolve API permission/rate/pagination issues before sending. |
| X_PERMISSION_OR_RECIPIENT_RESTRICTED | Check DM permissions, recipient settings, account/encryption requirements. |
| BUDGET_EXCEEDED | Review local estimates and provider billing before changing the allowance. |
| Dependency downloads stall on wheel metadata | This host required pip's legacy resolver; using --use-deprecated=legacy-resolver completed installation. Pinned offline-wheel installation was also tested. |

See docs/ARCHITECTURE.md, docs/VERIFICATION.md and docs/DEMO_SCRIPT.md before recording a submission. The current delivery contains a demo script and synthetic screenshots, not a fabricated live demo video.
