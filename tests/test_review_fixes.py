"""Fixes for the findings of the final review."""
import secrets
import subprocess
from datetime import timedelta
from zipfile import ZipFile

import pytest
from sqlalchemy import func, select

from app.errors import DomainError, ProviderError
from app.integrations.fixture import FixtureClient
from app.models import Account, FixtureMessage, Outreach, SearchResult, Workspace, now
from app.services import drafting, queue
from app.services.discovery import discover
from app.services.drafting import generate
from app.services.fit import validate_fit
from app.services.outreach import approve, create_outreach
from app.services.queue import enqueue, sync_due, tick
from app.services.runtime import Runtime
from app.services.sending import send


def spend(rt):
    with rt.factory() as db:
        return db.get(Workspace, "main").spend_micros


# ---------------------------------------------------------------- 1. phantom X budget reservations

def test_token_failure_reserves_no_budget(rt):
    live = Runtime(rt.factory, rt.settings.model_copy(update={"app_mode": "live"}))
    with pytest.raises(DomainError) as e:
        live.read("search", "robotics")
    assert e.value.code == "ACCOUNT_RECONNECT_REQUIRED"
    assert spend(rt) == 0


@pytest.mark.parametrize("code,status,kept", [
    ("RATE_LIMITED", 429, False), ("X_REQUEST_REJECTED", 500, False), ("X_CREDITS_REQUIRED", 402, False),
    ("X_NETWORK_UNCERTAIN", 503, True), ("X_MALFORMED_RESPONSE", 503, True),
])
def test_x_error_answers_release_their_reservation(rt, code, status, kept):
    class Failing(FixtureClient):
        def search(self, query, limit=50):
            raise ProviderError(code, status)
    rt.provider_override = Failing(rt.factory)
    with pytest.raises(ProviderError):
        rt.read("search", "robotics")
    assert spend(rt) == (750_000 if kept else 0)


def test_worker_backs_off_when_the_account_needs_reconnecting():
    assert queue.backs_off("held:ACCOUNT_RECONNECT_REQUIRED")
    assert queue.backs_off("error:OperationalError") and queue.backs_off("held:BUDGET_EXCEEDED")
    assert not queue.backs_off("held:PACING") and not queue.backs_off("sent")


def test_reply_checks_stop_at_the_first_failure_in_a_pass(rt):
    rt.settings.outreach_policy, rt.settings.send_min_gap_seconds = "operator_approved", 0
    discover(rt, "robotics, embodied AI")
    for person in ("fixture_ada", "fixture_mira"):
        oid = create_outreach(rt, person)
        generate(rt, oid, 0, "test-session")
        approve(rt, oid, 1)
        assert send(rt, oid, 1, secrets.token_urlsafe(24)) == "sent"

    class Down(FixtureClient):
        calls = 0

        def events(self, recipient, cursor=None):
            Down.calls += 1
            raise ProviderError("X_REQUEST_REJECTED", 500)
    rt.provider_override = Down(rt.factory)
    sync_due(rt)
    assert Down.calls == 1
    sync_due(rt)
    assert Down.calls == 2
    assert sync_due(rt) == 0 and Down.calls == 2


# ---------------------------------------------------------------- 2. 429 on send

def queued(rt, person):
    discover(rt, "robotics, embodied AI")
    oid = create_outreach(rt, "fixture_" + person)
    generate(rt, oid, 0, "test-session")
    enqueue(rt, oid, 1)
    return oid


class RateLimited(FixtureClient):
    calls = 0
    retry_at = None

    def send(self, recipient, text):
        RateLimited.calls += 1
        if RateLimited.calls == 1:
            raise ProviderError("RATE_LIMITED", 429, True, retry_at=RateLimited.retry_at)
        return super().send(recipient, text)


@pytest.fixture
def op(rt):
    rt.settings.outreach_policy, rt.settings.send_min_gap_seconds = "operator_approved", 0
    RateLimited.calls, RateLimited.retry_at = 0, None
    rt.provider_override = RateLimited(rt.factory)
    return rt


def test_rate_limit_without_reset_time_keeps_the_message_queued_and_waits(op):
    first, second = queued(op, "ada"), queued(op, "mira")
    key = None
    with op.factory() as db:
        key = db.get(Outreach, first).queue_key
    assert tick(op) == "held:RATE_LIMITED"
    with op.factory() as db:
        held = db.get(Outreach, first)
        assert held.queued_at and held.queue_key and held.queue_key != key and held.approved_hash
        assert held.queue_note == "RATE_LIMITED"
        wait = db.get(Account, "fixture_sender").cooldown_until - now()
        assert timedelta(minutes=14) < wait <= timedelta(minutes=15)
    assert tick(op) == "held:RATE_LIMITED" and RateLimited.calls == 1
    with op.factory.begin() as db:
        db.get(Account, "fixture_sender").cooldown_until = now() - timedelta(seconds=1)
    assert tick(op) == "sent"
    with op.factory() as db:
        assert db.get(Outreach, first).send_status == "sent" and db.get(Outreach, second).queued_at
        assert db.scalar(select(func.count()).select_from(FixtureMessage)) == 1


def test_rate_limit_reset_time_from_x_is_used(op):
    RateLimited.retry_at = now() + timedelta(minutes=40)
    queued(op, "ada")
    assert tick(op) == "held:RATE_LIMITED"
    with op.factory() as db:
        assert db.get(Account, "fixture_sender").cooldown_until == RateLimited.retry_at


def test_rate_limit_seen_after_a_restart_is_requeued_not_dropped(op):
    oid = queued(op, "ada")
    with op.factory() as db:
        key = db.get(Outreach, oid).queue_key
    assert send(op, oid, 1, key) == "rejected"
    assert tick(op) == "held:RATE_LIMITED"
    with op.factory() as db:
        row = db.get(Outreach, oid)
        assert row.queued_at and row.queue_key != key and row.approved_hash


# ---------------------------------------------------------------- 3. OpenAI request shape is covered in test_openai.py

# ---------------------------------------------------------------- 4. quote check strength

@pytest.fixture
def ai(rt):
    rt.settings.draft_provider, rt.settings.gemini_api_key = "gemini", "test-key"
    return rt


def model_says(monkeypatch, text, quote):
    def fake(rt, kind, system, payload, max_tokens=4096, strong=False):
        # Cite the post that really contains the quote, so only the rule under test can reject it.
        source_id = next((sid for sid, post in payload["sources"].items() if quote in post),
                         next(iter(payload["sources"])))
        return {"draft_text": text, "claims": [{"source_id": source_id, "quote": quote}], "uncertainties": []}
    monkeypatch.setattr(drafting, "complete_json", fake)


def ada_draft(rt):
    discover(rt, "robotics, embodied AI")
    oid = create_outreach(rt, "fixture_ada")
    generate(rt, oid, 0, "test-session")
    with rt.factory() as db:
        return db.get(Outreach, oid)


GOOD = "Hi Ada, your manipulation benchmark caught my eye. Open to a chat? Reply STOP to opt out."


def test_a_tiny_quote_does_not_count_as_evidence(ai, monkeypatch):
    model_says(monkeypatch, GOOD, "open")
    assert ada_draft(ai).draft_meta["provider"] == "evidence template"


def test_a_real_quote_of_enough_length_is_accepted(ai, monkeypatch):
    model_says(monkeypatch, GOOD, "I'm building an open robotics")
    assert ada_draft(ai).draft_meta["provider"] == "gemini"


@pytest.mark.parametrize("text", [
    "Hi Ada, see https://example.com for our fund. Reply STOP to opt out.",
    "Hi Ada, visit www.example.com soon. Reply STOP to opt out.",
    "Hi Ada, my colleague @someone says hello. Reply STOP to opt out.",
])
def test_ai_drafts_with_links_or_mentions_fall_back(ai, monkeypatch, text):
    model_says(monkeypatch, text, "I'm building an open robotics")
    assert ada_draft(ai).draft_meta["provider"] == "evidence template"


def test_claims_are_kept_with_the_draft_and_shown_for_review(ai, monkeypatch):
    model_says(monkeypatch, GOOD, "I'm building an open robotics")
    row = ada_draft(ai)
    assert row.draft_meta["provider"] == "gemini"
    assert row.draft_meta["claims"] == [{"source_id": "p_ada_1", "quote": "I'm building an open robotics"}]


def test_fit_judgment_with_a_tiny_quote_is_dropped():
    raw = {"people": [{"candidate_id": "fixture_ada", "fit": "strong", "role": "researcher", "reason": "Builds.",
                       "quotes": [{"source_id": "p_ada_1", "quote": "open"}]}]}
    assert validate_fit(raw, {"fixture_ada": {"p_ada_1": "I'm building an open robotics benchmark."}}) == {}


def test_review_card_shows_what_the_draft_relies_on(rt, monkeypatch):
    import re
    from fastapi.testclient import TestClient
    from app.main import create_app
    from conftest import TEST_PASSWORD
    rt.settings.draft_provider, rt.settings.gemini_api_key = "gemini", "test-key"
    model_says(monkeypatch, GOOD, "I'm building an open robotics")
    ada_draft(rt)
    with rt.factory.begin() as db:
        for result in db.scalars(select(SearchResult)):
            result.ai_fit = "strong" if result.candidate_id == "fixture_ada" else None
    with TestClient(create_app(rt.settings, rt.factory)) as client:
        csrf = re.search(r'name="csrf" value="([^"]+)"', client.get("/login").text)[1]
        client.post("/login", data={"csrf": csrf, "password": TEST_PASSWORD})
        page = client.get("/review").text
    assert "Draft relies on" in page and "I&#39;m building an open robotics" in page


# ---------------------------------------------------------------- packaging: tracked files only

def test_archive_contains_only_files_tracked_by_git(tmp_path):
    from scripts.package import build
    root = tmp_path / "project"
    (root / "app").mkdir(parents=True)
    (root / "app" / "main.py").write_text("print()", encoding="utf-8")
    (root / ".env.example").write_text("GEMINI_API_KEY=\n", encoding="utf-8")
    (root / "Assignment brief.pdf").write_text("not ours to ship", encoding="utf-8")
    (root / "PERSONAL_NOTES.md").write_text("private", encoding="utf-8")
    git = ["git", "-C", str(root)]
    subprocess.run(git + ["init", "-q"], check=True)
    subprocess.run(git + ["add", "app/main.py", ".env.example"], check=True)
    destination = tmp_path / "out.zip"
    build(root, destination)
    with ZipFile(destination) as archive:
        assert {n.split("/", 1)[1] for n in archive.namelist()} == {"app/main.py", ".env.example"}
