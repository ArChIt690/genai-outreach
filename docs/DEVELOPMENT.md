# Development

For running without Docker, running the tests, and publishing the Docker image. Users only need the README.

## Running without Docker

Needs Python 3.12 and PostgreSQL 16 or newer (tested on 18).

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.lock
createdb -U <your postgres user> outreach
.venv\Scripts\python.exe -m scripts.bootstrap --fixture-demo --database-url "postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/outreach"
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log
```

- On macOS or Linux use `.venv/bin/python`. On Windows with several Pythons installed: `py -3.12 -m venv .venv`.
- For live mode, create a separate database (e.g. `outreach_live`) and point `DATABASE_URL` in `.env` at it; a database is tied to the mode it was first used in.
- Keep `--no-access-log`: it stops X sign-in codes from being written to logs. Run one app process; the send queue runs inside it.
- If `OPENAI_API_KEY` or `GEMINI_API_KEY` is also set in your operating system's environment variables, that value overrides `.env`. Remove it and restart from a new terminal.
- Numeric X ID for the test list: `.venv\Scripts\python.exe -m scripts.x_user_id @handle`.
- Change the password: `.venv\Scripts\python.exe -m scripts.bootstrap --reset-password`.

## Tests

The tests use synthetic data and fake AI and X servers, never call real services, and remove real keys from their environment.

```
$env:TEST_DATABASE_URL="postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/outreach_test"
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check .
```

The test database name must start with `outreach_test`; it is emptied on every run. Browser tests use Microsoft Edge on Windows, or set `BROWSER_EXECUTABLE`; skip them with `-m "not browser"`.

## Docker commands

- Stop: `Ctrl+C` or `docker compose down`. Delete all data: `docker compose down -v`.
- Newest published image: `docker compose pull`, then `docker compose up`.
- Run local code changes instead of the published image: `docker compose up --build`.
- On Linux, if `.env` can't be written by the setup step: `docker compose run --rm --user "$(id -u):$(id -g)" setup`.

## Publishing the Docker image

After code changes, from a clean checkout of committed code (needs `docker login` as the image owner):

```
docker buildx build --platform linux/amd64,linux/arm64 -t archit690/genai-outreach:latest --push .
```
