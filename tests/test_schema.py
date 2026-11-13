import importlib.util
from pathlib import Path

from sqlalchemy import inspect, text

from app.config import Settings

MIGRATION = Path(__file__).resolve().parent.parent / "migrations" / "versions" / "0002_assisted_outreach.py"


def load_migration():
    spec = importlib.util.spec_from_file_location("migration_0002", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_new_settings_defaults():
    s = Settings(_env_file=None)
    assert (s.outreach_policy, s.draft_provider) == ("test_allowlist", "template")
    assert (s.daily_send_limit, s.send_min_gap_seconds, s.auto_sync_minutes) == (10, 120, 180)
    assert (s.gemini_model, s.gemini_fallback_model) == ("gemini-flash-latest", "gemini-2.5-flash")
    assert s.draft_limit_per_session == 40
    assert (s.queue_tick_seconds, s.ai_daily_call_limit, s.worker_enabled) == (30, 200, True)
    assert s.gemini_api_key == ""


def test_gemini_is_an_accepted_draft_provider():
    assert Settings(_env_file=None, draft_provider="gemini").draft_provider == "gemini"


def test_migration_0002_is_safe_to_repeat(database):
    engine, _, _ = database
    migration = load_migration()
    assert (migration.revision, migration.down_revision) == ("0002", "0001")
    # Put the database back to its pre-0002 shape for a sample of the changes.
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS ai_calls"))
        connection.execute(text("ALTER TABLE outreach DROP COLUMN IF EXISTS queued_at"))
        connection.execute(text("ALTER TABLE outreach DROP COLUMN IF EXISTS skipped"))
        connection.execute(text("ALTER TABLE search_results DROP COLUMN IF EXISTS ai_fit"))
    for _ in range(2):
        with engine.begin() as connection:
            migration.apply(connection)
    found = inspect(engine)
    assert "ai_calls" in found.get_table_names()
    outreach = {c["name"]: c for c in found.get_columns("outreach")}
    assert {"skipped", "queued_at", "queue_key", "queue_note"} <= set(outreach)
    assert outreach["skipped"]["nullable"] is False
    results = {c["name"] for c in found.get_columns("search_results")}
    assert {"ai_fit", "ai_role", "ai_reason", "ai_quotes"} <= results
    calls = {c["name"] for c in found.get_columns("ai_calls")}
    assert {"kind", "provider", "model", "input_tokens", "output_tokens", "latency_ms", "outcome", "error",
            "created"} <= calls
