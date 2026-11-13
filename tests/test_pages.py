import re
import secrets

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.integrations.llm import LLMError
from app.main import create_app
from app.models import AICall, Outreach, SearchResult, Suppression
from app.security import digest
from app.services import fit
from app.services.discovery import discover
from app.services.drafting import generate
from app.services.outreach import create_outreach
from app.services.queue import enqueue
from app.services.sending import send
from conftest import TEST_PASSWORD

ADA_REASON = "Building an open manipulation benchmark and releasing evaluation scripts."
ADA_QUOTE = "open robotics manipulation benchmark"


@pytest.fixture
def client(rt):
    app = create_app(rt.settings, rt.factory)
    with TestClient(app) as client:
        page = client.get("/login")
        csrf = re.search(r'name="csrf" value="([^"]+)"', page.text)[1]
        assert client.post("/login", data={"csrf": csrf, "password": TEST_PASSWORD},
                           follow_redirects=False).status_code == 303
        client.csrf = re.search(r'name="csrf" value="([^"]+)"', client.get("/discover").text)[1]
        yield client


def post(client, path, **data):
    return client.post(path, data={"csrf": client.csrf, **data}, follow_redirects=False)


def judged_search(rt):
    """A search whose results carry AI judgments: Ada strong, Mira weak, the news account weak."""
    run = discover(rt, "robotics, embodied AI")
    with rt.factory.begin() as db:
        for result in db.scalars(select(SearchResult).where(SearchResult.run_id == run)):
            if result.candidate_id == "fixture_ada":
                result.ai_fit, result.ai_role, result.ai_reason = "strong", "researcher", ADA_REASON
                result.ai_quotes = [{"source_id": "p_ada_1", "quote": ADA_QUOTE}]
            else:
                result.ai_fit, result.ai_role, result.ai_reason = "weak", "other", "Not first-hand work."
                result.ai_quotes = []
    return run


def drafted(rt, person="ada"):
    oid = create_outreach(rt, "fixture_" + person)
    generate(rt, oid, 0, "test-session")
    return oid


def outreach(rt, oid):
    with rt.factory() as db:
        return db.get(Outreach, oid)


def test_review_lists_pending_draft_with_reason(client, rt):
    judged_search(rt)
    oid = drafted(rt)
    page = client.get("/review")
    assert page.status_code == 200
    for expected in ("Ada Tan", "@ada_robotics", "strong", "researcher", ADA_REASON, ADA_QUOTE,
                     "your public post says:", "Approve and queue", "Save edit", "Skip", "Do not contact",
                     f'formaction="/outreach/{oid}/queue"', "evidence template"):
        assert expected in page.text, expected


def test_review_is_empty_without_drafts_and_requires_sign_in(client, rt):
    assert "Nothing is waiting for review" in client.get("/review").text
    client.cookies.clear()
    assert client.get("/review", follow_redirects=False).headers["location"] == "/login"


def test_review_card_is_blocked_under_the_test_list_rule(client, rt):
    judged_search(rt)
    drafted(rt)
    page = client.get("/review").text
    assert "recipient not allowed" in page
    assert re.search(r'formaction="/outreach/[^"]+/queue"[^>]*disabled', page)


def test_queue_action_queues_and_returns_to_review(client, rt):
    rt.settings.outreach_policy = "operator_approved"
    judged_search(rt)
    oid = drafted(rt)
    response = post(client, f"/outreach/{oid}/queue", version="1", next="review")
    assert response.status_code == 303 and response.headers["location"].startswith("/review")
    row = outreach(rt, oid)
    assert row.queued_at and row.approved_hash == digest(row.draft)
    assert "Ada Tan" not in client.get("/review").text.split("Waiting to send")[0]


def test_queue_action_approves_the_text_that_was_on_screen(client, rt):
    rt.settings.outreach_policy = "operator_approved"
    judged_search(rt)
    oid = drafted(rt)
    edited = "Hi Ada, your benchmark release caught my eye. Could we talk? Reply STOP to opt out."
    response = post(client, f"/outreach/{oid}/queue", version="1", next="review", text=edited)
    assert response.status_code == 303
    row = outreach(rt, oid)
    assert (row.draft, row.version) == (edited, 2)
    assert row.queued_at and row.approved_hash == digest(edited)


def test_queue_action_blocked_shows_reason(client, rt):
    judged_search(rt)
    oid = drafted(rt)
    response = post(client, f"/outreach/{oid}/queue", version="1", next="review")
    assert response.status_code == 409 and "RECIPIENT_NOT_ALLOWED" in response.text
    assert outreach(rt, oid).queued_at is None


def test_skip_removes_card(client, rt):
    judged_search(rt)
    oid = drafted(rt)
    response = post(client, f"/outreach/{oid}/skip", version="1", next="review")
    assert response.status_code == 303 and response.headers["location"].startswith("/review")
    assert outreach(rt, oid).skipped is True
    assert "Ada Tan" not in client.get("/review").text


def test_do_not_contact_from_review_returns_to_review(client, rt):
    judged_search(rt)
    drafted(rt)
    response = post(client, "/candidates/fixture_ada/suppress", next="review")
    assert response.headers["location"].startswith("/review")
    with rt.factory() as db:
        assert db.get(Suppression, "fixture_ada")


def test_save_edit_from_review_returns_to_review(client, rt):
    judged_search(rt)
    oid = drafted(rt)
    response = post(client, f"/outreach/{oid}/edit", version="1", next="review",
                    text="A shorter note. Reply STOP to opt out.")
    assert response.headers["location"].startswith("/review")
    assert outreach(rt, oid).draft == "A shorter note. Reply STOP to opt out."


def test_review_next_param_cannot_redirect_elsewhere(client, rt):
    judged_search(rt)
    oid = drafted(rt)
    response = post(client, f"/outreach/{oid}/edit", version="1", next="https://evil.example",
                    text="A shorter note. Reply STOP to opt out.")
    assert response.headers["location"] == "/candidates/fixture_ada"


def test_batch_draft_action_reports_counts(client, rt):
    run = judged_search(rt)
    response = post(client, f"/searches/{run}/draft")
    assert response.status_code == 303 and response.headers["location"].startswith("/review?notice=")
    page = client.get(response.headers["location"]).text
    assert "1 drafted" in page and "Ada Tan" in page and "Mira Nguyen" not in page


def test_unqueue_action_returns_to_activity(client, rt):
    rt.settings.outreach_policy = "operator_approved"
    judged_search(rt)
    oid = drafted(rt)
    enqueue(rt, oid, 1)
    response = post(client, f"/outreach/{oid}/unqueue", next="activity")
    assert response.headers["location"].startswith("/activity")
    assert outreach(rt, oid).queued_at is None


def test_sync_all_action(client, rt, prepared):
    assert send(rt, prepared, 1, secrets.token_urlsafe(24)) == "sent"
    response = post(client, "/activity/sync")
    assert response.status_code == 303 and response.headers["location"].startswith("/activity?notice=")
    assert "1 conversation checked" in client.get(response.headers["location"]).text
    assert outreach(rt, prepared).last_sync


def test_activity_shows_queue_position_hold_and_attention(client, rt):
    rt.settings.outreach_policy = "operator_approved"
    rt.settings.send_enabled = False
    judged_search(rt)
    ada, mira = drafted(rt, "ada"), drafted(rt, "mira")
    enqueue(rt, ada, 1)
    enqueue(rt, mira, 1)
    page = client.get("/activity").text
    assert "Queued, 1 of 2" in page and "Queued, 2 of 2" in page
    assert "sending disabled" in page and "Sync all now" in page
    with rt.factory.begin() as db:
        row = db.get(Outreach, mira)
        row.queued_at, row.queue_key, row.queue_note = None, None, "DO_NOT_CONTACT"
    attention = client.get("/activity?attention=1").text
    assert "Mira Nguyen" in attention and "do not contact" in attention and "Ada Tan" not in attention


def test_settings_shows_send_rule_and_ai_usage(client, rt):
    with rt.factory.begin() as db:
        db.add(AICall(kind="fit", provider="gemini", model="gemini-flash-latest", input_tokens=900,
                      output_tokens=100, latency_ms=1500, outcome="ok"))
        db.add(AICall(kind="draft", provider="gemini", model="gemini-2.5-flash", input_tokens=400,
                      output_tokens=100, latency_ms=2500, outcome="fallback_model", error="HTTP_503"))
        db.add(AICall(kind="draft", provider="gemini", model="gemini-2.5-flash", latency_ms=500,
                      outcome="failed", error="AI_BAD_RESPONSE"))
    page = client.get("/settings").text
    for expected in ("Test list only", "AI usage", "gemini-2.5-flash", "1,500", "AI_BAD_RESPONSE",
                     "Every 180 minutes", "120 seconds"):
        assert expected in page, expected
    usage = re.search(r'<dl class="settings-list usage-totals">(.*?)</dl>', page, re.S)[1]
    assert re.findall(r"<dd>([^<]*)</dd>", usage) == ["3", "1,500", "1,500 ms", "1", "1"]
    rt.settings.outreach_policy = "operator_approved"
    assert "Operator-approved sending" in client.get("/settings").text


def test_navigation_shows_review_count_and_send_rule(client, rt):
    judged_search(rt)
    drafted(rt)
    page = client.get("/discover").text
    assert 'href="/review"' in page and "1 waiting" in page and "Test list only" in page


def test_discover_orders_by_ai_fit_and_offers_batch_drafting(client, rt):
    run = judged_search(rt)
    page = client.get(f"/discover?run={run}").text
    assert page.index("Ada Tan") < page.index("Mira Nguyen")
    assert ADA_REASON in page and ADA_QUOTE in page
    assert f'action="/searches/{run}/draft"' in page and "Draft for top matches" in page


def test_search_action_runs_ai_judging(client, rt, monkeypatch):
    rt.settings.draft_provider, rt.settings.gemini_api_key = "gemini", "test-key"
    monkeypatch.setattr(fit, "complete_json", lambda *a, **k: {"people": [{
        "candidate_id": "fixture_ada", "fit": "strong", "role": "researcher", "reason": ADA_REASON,
        "quotes": [{"source_id": "p_ada_1", "quote": ADA_QUOTE}]}]})
    response = post(client, "/searches", topics="robotics, embodied AI")
    assert response.status_code == 303
    with rt.factory() as db:
        fits = {r.candidate_id: r.ai_fit for r in db.scalars(select(SearchResult))}
    assert fits["fixture_ada"] == "strong" and fits["fixture_mira"] is None
    assert ADA_REASON in client.get(response.headers["location"]).text


def test_search_says_when_ai_judging_was_unavailable(client, rt, monkeypatch):
    rt.settings.draft_provider, rt.settings.gemini_api_key = "gemini", "test-key"

    def down(*args, **kwargs):
        raise LLMError("AI_UNAVAILABLE")
    monkeypatch.setattr(fit, "complete_json", down)
    response = post(client, "/searches", topics="robotics, embodied AI")
    page = client.get(response.headers["location"]).text
    assert "AI fit judging was unavailable" in page and "Ada Tan" in page


def test_new_actions_require_csrf(client, rt):
    run = judged_search(rt)
    oid = drafted(rt)
    for path in (f"/outreach/{oid}/queue", f"/outreach/{oid}/unqueue", f"/outreach/{oid}/skip",
                 f"/searches/{run}/draft", "/activity/sync"):
        assert client.post(path, data={"version": "1"}).status_code == 403, path
        assert client.post(path, data={"version": "1", "csrf": client.csrf},
                           headers={"origin": "https://attacker.example"}).status_code == 403, path
    assert outreach(rt, oid).queued_at is None and outreach(rt, oid).skipped is False
