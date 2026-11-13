import pytest
from sqlalchemy import select

from app.integrations.llm import LLMError
from app.models import SearchResult
from app.services import fit
from app.services.discovery import discover
from app.services.fit import fit_rank, judge, validate_fit

ADA = {"candidate_id": "fixture_ada", "fit": "strong", "role": "researcher",
       "reason": "Building an open manipulation benchmark and releasing evaluation scripts.",
       "quotes": [{"source_id": "p_ada_1", "quote": "open robotics manipulation benchmark"}]}
MIRA = {"candidate_id": "fixture_mira", "fit": "possible", "role": "researcher",
        "reason": "Researches embodied AI policies in simulation.",
        "quotes": [{"source_id": "p_mira", "quote": "I'm researching embodied AI."}]}
NEWS = {"candidate_id": "fixture_news", "fit": "weak", "role": "not_a_person",
        "reason": "A news account reporting on others.", "quotes": []}


@pytest.fixture
def gemini(rt):
    rt.settings.draft_provider = "gemini"
    rt.settings.gemini_api_key = "test-key"
    return rt


def answer(monkeypatch, *people, error=None):
    """Make the model return these people; collect what it was asked."""
    asked = []

    def fake(rt, kind, system, payload, max_tokens=4096):
        asked.append((kind, system, payload))
        if error:
            raise error
        return {"people": list(people)}
    monkeypatch.setattr(fit, "complete_json", fake)
    return asked


def stored(rt, run):
    with rt.factory() as db:
        return {r.candidate_id: r for r in db.scalars(select(SearchResult).where(SearchResult.run_id == run))}


def test_valid_judgments_are_stored(gemini, monkeypatch):
    asked = answer(monkeypatch, ADA, MIRA, NEWS)
    run = discover(gemini, "robotics, embodied AI")
    assert judge(gemini, run) == 3
    rows = stored(gemini, run)
    ada = rows["fixture_ada"]
    assert (ada.ai_fit, ada.ai_role, ada.ai_reason) == ("strong", "researcher", ADA["reason"])
    assert ada.ai_quotes == ADA["quotes"]
    assert (rows["fixture_news"].ai_fit, rows["fixture_news"].ai_role) == ("weak", "not_a_person")
    [(kind, system, payload)] = asked
    assert kind == "fit" and "untrusted" in system.lower()
    people = {p["candidate_id"]: p for p in payload["people"]}
    assert {"source_id": "p_ada_1", "text": "I'm building an open robotics manipulation benchmark. "
            "Released our first evaluation scripts today."} in people["fixture_ada"]["posts"]


def test_invented_quote_drops_only_that_person(gemini, monkeypatch):
    invented = dict(ADA, quotes=[{"source_id": "p_ada_1", "quote": "never said this"}])
    answer(monkeypatch, invented, MIRA)
    run = discover(gemini, "robotics, embodied AI")
    assert judge(gemini, run) == 1
    rows = stored(gemini, run)
    assert rows["fixture_ada"].ai_fit is None and rows["fixture_ada"].ai_reason is None
    assert rows["fixture_mira"].ai_fit == "possible"


def test_quote_from_another_persons_post_is_rejected(gemini, monkeypatch):
    borrowed = dict(ADA, quotes=[{"source_id": "p_mira", "quote": "I'm researching embodied AI."}])
    answer(monkeypatch, borrowed)
    run = discover(gemini, "robotics, embodied AI")
    assert judge(gemini, run) == 0


def test_unknown_and_repeated_people_are_ignored(gemini, monkeypatch):
    stranger = dict(MIRA, candidate_id="stranger")
    answer(monkeypatch, stranger, ADA, dict(ADA, fit="possible"), MIRA)
    run = discover(gemini, "robotics, embodied AI")
    assert judge(gemini, run) == 1
    rows = stored(gemini, run)
    assert rows["fixture_ada"].ai_fit is None and rows["fixture_mira"].ai_fit == "possible"
    assert "stranger" not in rows


def test_strong_without_quote_is_dropped(gemini, monkeypatch):
    answer(monkeypatch, dict(ADA, quotes=[]))
    run = discover(gemini, "robotics, embodied AI")
    assert judge(gemini, run) == 0
    assert stored(gemini, run)["fixture_ada"].ai_fit is None


def test_news_account_called_a_strong_fit_is_dropped(gemini, monkeypatch):
    confused = dict(NEWS, fit="strong", quotes=[{"source_id": "p_news", "quote": "new robotics benchmark"}])
    answer(monkeypatch, confused)
    run = discover(gemini, "robotics, embodied AI")
    assert judge(gemini, run) == 0


@pytest.mark.parametrize("raw", [{}, {"people": "nope"}, {"people": [1, None, {"candidate_id": "fixture_ada"}]}, []])
def test_malformed_answers_store_nothing(raw):
    assert validate_fit(raw, {"fixture_ada": {"p_ada_1": "some text"}}) == {}


def test_ai_failure_keeps_keyword_results(gemini, monkeypatch):
    answer(monkeypatch, error=LLMError("AI_UNAVAILABLE"))
    run = discover(gemini, "robotics, embodied AI")
    assert judge(gemini, run) == 0
    rows = stored(gemini, run)
    assert rows["fixture_ada"].score >= 7 and rows["fixture_ada"].ai_fit is None


def test_empty_search_makes_no_ai_call(gemini, monkeypatch):
    asked = answer(monkeypatch, ADA)
    run = discover(gemini, "underwater weaving")
    assert judge(gemini, run) == 0 and asked == []


def test_template_provider_makes_no_ai_call(rt, monkeypatch):
    asked = answer(monkeypatch, ADA)
    run = discover(rt, "robotics, embodied AI")
    assert judge(rt, run) == 0 and asked == []


def test_only_public_profile_and_posts_reach_the_model(gemini, monkeypatch):
    asked = answer(monkeypatch, ADA)
    judge(gemini, discover(gemini, "robotics, embodied AI"))
    text = str(asked[0][2])
    assert "test-key" not in text and "dm_events" not in text and "Singapore" not in text


def test_fit_rank_order():
    assert [fit_rank(x) for x in ("strong", "possible", None, "weak")] == [0, 1, 2, 3]
