"""Rewrite a draft with the stronger model, optionally following the reviewer's note."""
import pytest

from app.errors import DomainError
from app.integrations.llm import LLMError
from app.models import Outreach
from app.services import drafting
from app.services.discovery import discover
from app.services.drafting import generate, rewrite
from app.services.outreach import create_outreach, save_draft
from app.services.queue import enqueue

NEW_TEXT = "Hi Ada, your grasp recovery tests caught my eye. Open to a short chat? Reply STOP to opt out."


@pytest.fixture
def openai(rt):
    rt.settings.draft_provider = "openai"
    rt.settings.openai_api_key = "test-openai-key"
    return rt


def model(monkeypatch, text=NEW_TEXT, error=None, claims=None):
    """Fake model: records each request and answers with this text."""
    asked = []

    def fake(rt, kind, system, payload, max_tokens=4096, strong=False):
        asked.append({"kind": kind, "system": system, "payload": payload, "strong": strong})
        if error:
            raise error
        source_id, post = next(iter(payload["sources"].items()))
        return {"draft_text": text, "claims": claims or [{"source_id": source_id, "quote": post[:20]}],
                "uncertainties": []}
    monkeypatch.setattr(drafting, "complete_json", fake)
    return asked


def drafted(rt):
    discover(rt, "robotics, embodied AI")
    oid = create_outreach(rt, "fixture_ada")
    generate(rt, oid, 0, "test-session")
    return oid


def row(rt, oid):
    with rt.factory() as db:
        return db.get(Outreach, oid)


def test_rewrite_uses_the_strong_model_and_the_note(openai, monkeypatch):
    asked = model(monkeypatch)
    oid = drafted(openai)
    old = row(openai, oid).draft
    assert rewrite(openai, oid, 1, "test-session", "  shorter, mention the grasp tests ") == 2
    request = asked[-1]
    assert (request["kind"], request["strong"]) == ("rewrite", True)
    assert request["payload"]["reviewer_note"] == "shorter, mention the grasp tests"
    assert request["payload"]["current_draft"] == old
    assert "reviewer_note" in request["system"] and "untrusted" in request["system"].lower()
    after = row(openai, oid)
    assert after.draft == NEW_TEXT and after.version == 2 and after.approved_hash is None
    assert after.draft_meta["provider"] == "openai" and after.draft_meta["model"] == "gpt-6.1-terra"
    assert after.draft_meta["rewrite_note"] == "shorter, mention the grasp tests"
    assert after.draft_meta["fallback"] is None


def test_rewrite_without_a_note(openai, monkeypatch):
    asked = model(monkeypatch)
    oid = drafted(openai)
    rewrite(openai, oid, 1, "test-session")
    assert asked[-1]["payload"]["reviewer_note"] == ""


def test_rewrite_is_never_served_from_the_cache(openai, monkeypatch):
    asked = model(monkeypatch)
    oid = drafted(openai)
    rewrite(openai, oid, 1, "test-session")
    rewrite(openai, oid, 2, "test-session")
    assert [a["kind"] for a in asked].count("rewrite") == 2


def test_failed_rewrite_keeps_the_current_draft(openai, monkeypatch):
    model(monkeypatch, error=LLMError("AI_UNAVAILABLE"))
    oid = drafted(openai)
    before = row(openai, oid)
    with pytest.raises(DomainError) as e:
        rewrite(openai, oid, 1, "test-session")
    assert e.value.code == "AI_UNAVAILABLE" and "unchanged" in e.value.message
    after = row(openai, oid)
    assert (after.draft, after.version) == (before.draft, before.version)


def test_rewrite_with_an_invented_quote_keeps_the_current_draft(openai, monkeypatch):
    model(monkeypatch, claims=[{"source_id": "p_ada_1", "quote": "never said this"}])
    oid = drafted(openai)
    before = row(openai, oid).draft
    with pytest.raises(DomainError) as e:
        rewrite(openai, oid, 1, "test-session")
    assert e.value.code == "AI_BAD_RESPONSE" and row(openai, oid).draft == before


@pytest.mark.parametrize("text", ["Hi Ada. " + "x" * 500 + " Reply STOP to opt out.", "Hi Ada, chat soon?"])
def test_rewrite_still_needs_length_and_opt_out(openai, monkeypatch, text):
    model(monkeypatch, text=text)
    oid = drafted(openai)
    with pytest.raises(DomainError) as e:
        rewrite(openai, oid, 1, "test-session")
    assert e.value.code == "AI_BAD_RESPONSE"


def test_rewrite_note_is_limited_to_300_characters(openai, monkeypatch):
    asked = model(monkeypatch)
    oid = drafted(openai)
    with pytest.raises(DomainError) as e:
        rewrite(openai, oid, 1, "test-session", "x" * 301)
    assert e.value.code == "INVALID_NOTE" and not [a for a in asked if a["kind"] == "rewrite"]


def test_rewrite_needs_ai_to_be_on(rt):
    oid = drafted(rt)
    with pytest.raises(DomainError) as e:
        rewrite(rt, oid, 1, "test-session")
    assert e.value.code == "AI_NOT_CONFIGURED"


def test_rewrite_of_a_stale_version_is_refused(openai, monkeypatch):
    model(monkeypatch)
    oid = drafted(openai)
    save_draft(openai, oid, 1, "Edited in another tab. Reply STOP to opt out.", source_ids=["p_ada_1"])
    with pytest.raises(DomainError) as e:
        rewrite(openai, oid, 1, "test-session")
    assert e.value.code == "APPROVAL_STALE"


def test_rewrite_takes_a_queued_draft_out_of_the_queue(openai, monkeypatch):
    openai.settings.outreach_policy = "operator_approved"
    model(monkeypatch)
    oid = drafted(openai)
    enqueue(openai, oid, 1)
    rewrite(openai, oid, 1, "test-session")
    assert row(openai, oid).queued_at is None


def test_rewrite_counts_toward_the_session_limit(openai, monkeypatch):
    model(monkeypatch)
    openai.settings.draft_limit_per_session = 1
    oid = drafted(openai)
    with pytest.raises(DomainError) as e:
        rewrite(openai, oid, 1, "test-session")
    assert e.value.code == "DRAFT_LIMIT"


def test_normal_drafts_still_use_luna(openai, monkeypatch):
    asked = model(monkeypatch)
    drafted(openai)
    assert [(a["kind"], a["strong"]) for a in asked] == [("draft", False)]
