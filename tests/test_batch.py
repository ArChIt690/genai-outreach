import pytest
from sqlalchemy import select

from app.errors import DomainError
from app.integrations.llm import LLMError
from app.models import Outreach, SearchResult
from app.services import drafting
from app.services.discovery import discover
from app.services.drafting import draft_batch, generate
from app.services.outreach import create_outreach, suppress


@pytest.fixture
def gemini(rt):
    rt.settings.draft_provider = "gemini"
    rt.settings.gemini_api_key = "test-key"
    return rt


def model_draft(payload, text=None):
    source_id, post = next(iter(payload["sources"].items()))
    first_name = payload["recipient"]["name"].split()[0]
    return {"draft_text": text or f"Hi {first_name}, your benchmark work caught my eye. Reply STOP to opt out.",
            "claims": [{"source_id": source_id, "quote": post[:25]}], "uncertainties": []}


def writer(monkeypatch, text=None, error=None, claims=None):
    """Make the model write drafts; collect what it was asked."""
    asked = []

    def fake(rt, kind, system, payload, max_tokens=4096):
        asked.append((kind, system, payload))
        if error:
            raise error
        answer = model_draft(payload, text)
        if claims is not None:
            answer["claims"] = claims
        return answer
    monkeypatch.setattr(drafting, "complete_json", fake)
    return asked


def outreach(rt, oid):
    with rt.factory() as db:
        return db.get(Outreach, oid)


def by_recipient(rt):
    with rt.factory() as db:
        return {o.recipient_id: o for o in db.scalars(select(Outreach))}


def set_fit(rt, run, **fits):
    with rt.factory.begin() as db:
        for row in db.scalars(select(SearchResult).where(SearchResult.run_id == run)):
            row.ai_fit = fits.get(row.candidate_id.removeprefix("fixture_"))


def ada(rt):
    discover(rt, "robotics, embodied AI")
    return create_outreach(rt, "fixture_ada")


def test_ai_draft_is_saved_when_quotes_check_out(gemini, monkeypatch):
    asked = writer(monkeypatch)
    oid = ada(gemini)
    assert generate(gemini, oid, 0, "test-session") == 1
    o = outreach(gemini, oid)
    assert o.draft == "Hi Ada, your benchmark work caught my eye. Reply STOP to opt out."
    assert (o.draft_meta["provider"], o.draft_meta["fallback"]) == ("gemini", None)
    assert o.draft_meta["model"] == "gemini-2.5-flash"
    [(kind, system, payload)] = asked
    assert kind == "draft" and "untrusted" in system.lower() and "500" in system and "Hi <first name>," in system
    assert set(payload) == {"recipient", "sender", "purpose", "sources"}
    assert "test-key" not in str(payload) and "Singapore" not in str(payload)


def test_ai_draft_over_500_chars_falls_back(gemini, monkeypatch):
    writer(monkeypatch, text="Hi Ada. " + "x" * 500 + " Reply STOP to opt out.")
    oid = ada(gemini)
    generate(gemini, oid, 0, "test-session")
    o = outreach(gemini, oid)
    assert o.draft_meta["provider"] == "evidence template" and o.draft_meta["fallback"]
    assert "your public post says:" in o.draft


def test_ai_draft_with_invented_quote_falls_back(gemini, monkeypatch):
    writer(monkeypatch, claims=[{"source_id": "p_ada_1", "quote": "never said this"}])
    oid = ada(gemini)
    generate(gemini, oid, 0, "test-session")
    assert outreach(gemini, oid).draft_meta["provider"] == "evidence template"


def test_ai_draft_without_opt_out_falls_back(gemini, monkeypatch):
    writer(monkeypatch, text="Hi Ada, your benchmark work caught my eye. Chat soon?")
    oid = ada(gemini)
    generate(gemini, oid, 0, "test-session")
    o = outreach(gemini, oid)
    assert o.draft_meta["provider"] == "evidence template" and "STOP" in o.draft


def test_ai_failure_falls_back_to_template(gemini, monkeypatch):
    writer(monkeypatch, error=LLMError("AI_UNAVAILABLE"))
    oid = ada(gemini)
    generate(gemini, oid, 0, "test-session")
    o = outreach(gemini, oid)
    assert "your public post says:" in o.draft and o.draft_meta["fallback"]


def test_unchanged_inputs_reuse_the_ai_draft_without_a_second_call(gemini, monkeypatch):
    asked = writer(monkeypatch)
    oid = ada(gemini)
    generate(gemini, oid, 0, "test-session")
    generate(gemini, oid, 1, "test-session")
    assert len(asked) == 1 and outreach(gemini, oid).draft_meta["cache_hit"] is True


def test_session_limit_comes_from_settings(rt):
    rt.settings.draft_limit_per_session = 1
    oid = ada(rt)
    generate(rt, oid, 0, "test-session")
    with pytest.raises(DomainError) as e:
        generate(rt, oid, 1, "test-session")
    assert e.value.code == "DRAFT_LIMIT"


def test_new_draft_brings_a_skipped_person_back(rt):
    oid = ada(rt)
    with rt.factory.begin() as db:
        db.get(Outreach, oid).skipped = True
    generate(rt, oid, 0, "test-session")
    assert outreach(rt, oid).skipped is False


def test_batch_drafts_strong_and_possible_only(gemini, monkeypatch):
    writer(monkeypatch)
    run = discover(gemini, "robotics, embodied AI")
    set_fit(gemini, run, ada="strong", mira="possible", news="weak")
    assert draft_batch(gemini, run, "test-session") == {"drafted": 2, "skipped": 0}
    rows = by_recipient(gemini)
    assert set(rows) == {"fixture_ada", "fixture_mira"}
    assert rows["fixture_ada"].draft.startswith("Hi Ada,") and rows["fixture_mira"].draft.startswith("Hi Mira,")


def test_batch_skips_suppressed_and_already_drafted(gemini, monkeypatch):
    writer(monkeypatch)
    run = discover(gemini, "robotics, embodied AI")
    set_fit(gemini, run, ada="strong", mira="possible", news="weak")
    suppress(gemini, "fixture_mira")
    assert draft_batch(gemini, run, "test-session") == {"drafted": 1, "skipped": 1}
    assert draft_batch(gemini, run, "test-session") == {"drafted": 0, "skipped": 2}
    assert set(by_recipient(gemini)) == {"fixture_ada"}


def test_batch_without_ai_uses_keyword_score(rt):
    run = discover(rt, "robotics, embodied AI")
    assert draft_batch(rt, run, "test-session") == {"drafted": 2, "skipped": 0}
    rows = by_recipient(rt)
    assert set(rows) == {"fixture_ada", "fixture_mira"}
    assert rows["fixture_ada"].draft_meta["provider"] == "evidence template"


def test_batch_continues_after_one_person_fails(gemini, monkeypatch):
    writer(monkeypatch)
    run = discover(gemini, "robotics, embodied AI")
    set_fit(gemini, run, ada="strong", mira="possible")
    real = drafting.generate

    def flaky(rt, oid, expected, session_hash):
        if outreach(rt, oid).recipient_id == "fixture_ada":
            raise DomainError("EVIDENCE_CHANGED", "changed")
        return real(rt, oid, expected, session_hash)
    monkeypatch.setattr(drafting, "generate", flaky)
    assert draft_batch(gemini, run, "test-session") == {"drafted": 1, "skipped": 1}


def test_batch_stops_at_the_session_limit(gemini, monkeypatch):
    writer(monkeypatch)
    gemini.settings.draft_limit_per_session = 1
    run = discover(gemini, "robotics, embodied AI")
    set_fit(gemini, run, ada="strong", mira="possible")
    assert draft_batch(gemini, run, "test-session") == {"drafted": 1, "skipped": 1}
