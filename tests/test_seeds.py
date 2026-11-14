"""Start a search from seed accounts: the model describes the seed, the app searches for similar people."""
import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import inspect, select, text

from app.errors import DomainError
from app.integrations.fixture import FixtureClient
from app.integrations.llm import LLMError
from app.models import AICall, SearchResult, SearchRun
from app.services import fit, seeds
from app.services.seeds import parse_handles, seed_search

PROFILE = {"summary": "Builds open robotics manipulation benchmarks and evaluation tools.",
           "topics": ["robotics", "manipulation benchmark"]}


@pytest.fixture
def ai(rt):
    rt.settings.draft_provider, rt.settings.gemini_api_key = "gemini", "test-key"
    return rt


def describe(monkeypatch, answer=PROFILE, error=None):
    asked = []

    def fake(rt, kind, system, payload, max_tokens=4096):
        asked.append((kind, system, payload))
        if error:
            raise error
        return answer
    monkeypatch.setattr(seeds, "complete_json", fake)
    return asked


def results(rt, run):
    with rt.factory() as db:
        return {r.candidate_id for r in db.scalars(select(SearchResult).where(SearchResult.run_id == run))}


@pytest.mark.parametrize("value,expected", [
    ("ada_robotics", ["ada_robotics"]), ("@ada_robotics, @noah_builds", ["ada_robotics", "noah_builds"]),
    (" ada_robotics  ada_robotics ", ["ada_robotics"]), ("https://x.com/ada_robotics", ["ada_robotics"]),
])
def test_parse_handles(value, expected):
    assert parse_handles(value) == expected


@pytest.mark.parametrize("value", ["", "   ", "has space!", "a,b,c,d", "x" * 16, "from:someone OR robots"])
def test_parse_handles_rejects_bad_input(value):
    with pytest.raises(DomainError) as e:
        parse_handles(value)
    assert e.value.code == "INVALID_SEED"


def test_seed_search_finds_similar_people_and_leaves_out_the_seed(ai, monkeypatch):
    asked = describe(monkeypatch)
    run = seed_search(ai, "@ada_robotics")
    assert results(ai, run) == {"fixture_mira", "fixture_news"}
    with ai.factory() as db:
        stored = db.get(SearchRun, run)
        assert stored.seed_handles == ["ada_robotics"] and stored.seed_summary == PROFILE["summary"]
        assert stored.terms == ["robotics", "manipulation benchmark"]
    [(kind, system, payload)] = asked
    assert kind == "seed" and "untrusted" in system.lower()
    [seed] = payload["seeds"]
    assert seed["handle"] == "ada_robotics" and seed["bio"].startswith("Robotics researcher")
    assert "I'm building an open robotics manipulation benchmark. Released our first evaluation scripts today." \
        in seed["posts"]
    assert "Singapore" not in str(payload) and "test-key" not in str(payload)


def test_seed_posts_are_read_with_a_small_limit(ai, monkeypatch):
    describe(monkeypatch)
    searches = []

    class Watching(FixtureClient):
        def search(self, query, limit=50):
            searches.append((query, limit))
            return super().search(query, limit)
    ai.provider_override = Watching(ai.factory)
    seed_search(ai, "ada_robotics")
    assert searches[0] == ("from:ada_robotics -is:retweet", 10)
    assert searches[1][1] == 50 and '"robotics"' in searches[1][0]


def test_two_seeds_are_described_together_and_both_left_out(ai, monkeypatch):
    asked = describe(monkeypatch)
    run = seed_search(ai, "ada_robotics, mira_models")
    assert [s["handle"] for s in asked[0][2]["seeds"]] == ["ada_robotics", "mira_models"]
    assert results(ai, run) == {"fixture_news"}


def test_unsafe_topics_from_the_model_are_dropped(ai, monkeypatch):
    describe(monkeypatch, {"summary": "Robotics.", "topics": ["robotics", "from:victim OR spam", "x" * 60, 7]})
    run = seed_search(ai, "ada_robotics")
    with ai.factory() as db:
        assert db.get(SearchRun, run).terms == ["robotics"]


@pytest.mark.parametrize("answer", [{"summary": "x", "topics": []}, {"summary": "x", "topics": ["has:links"]},
                                    {"topics": ["robotics"]}, {"summary": "", "topics": ["robotics"]}, {}])
def test_unusable_model_answer_runs_no_search(ai, monkeypatch, answer):
    describe(monkeypatch, answer)
    with pytest.raises(DomainError) as e:
        seed_search(ai, "ada_robotics")
    assert e.value.code == "SEED_FAILED"
    with ai.factory() as db:
        assert db.scalars(select(SearchRun)).all() == []


def test_model_failure_runs_no_search(ai, monkeypatch):
    describe(monkeypatch, error=LLMError("AI_UNAVAILABLE"))
    with pytest.raises(DomainError) as e:
        seed_search(ai, "ada_robotics")
    assert e.value.code == "AI_UNAVAILABLE"


def test_seed_search_needs_ai_and_spends_nothing_without_it(rt, monkeypatch):
    asked = describe(monkeypatch)

    class NoCalls(FixtureClient):
        def user(self, handle):
            pytest.fail("X was read although AI is off")
    rt.provider_override = NoCalls(rt.factory)
    with pytest.raises(DomainError) as e:
        seed_search(rt, "ada_robotics")
    assert e.value.code == "AI_NOT_CONFIGURED" and asked == []


def test_unknown_seed_is_reported_by_name(ai, monkeypatch):
    asked = describe(monkeypatch)
    with pytest.raises(DomainError) as e:
        seed_search(ai, "nobody_here")
    assert e.value.code == "SEED_NOT_FOUND" and "nobody_here" in e.value.message and asked == []


def test_seed_without_recent_posts_is_reported(ai, monkeypatch):
    asked = describe(monkeypatch)
    with pytest.raises(DomainError) as e:
        seed_search(ai, "test_recipient")
    assert e.value.code == "SEED_EMPTY" and asked == []


def test_fit_judging_is_told_about_the_seed(ai, monkeypatch):
    describe(monkeypatch)
    judged = []

    def fake(rt, kind, system, payload, max_tokens=4096):
        judged.append((system, payload))
        return {"people": []}
    monkeypatch.setattr(fit, "complete_json", fake)
    fit.judge(ai, seed_search(ai, "ada_robotics"))
    system, payload = judged[0]
    assert payload["seed_profile"] == PROFILE["summary"] and "seed_profile" in system


def test_ordinary_search_sends_no_seed_profile(ai, monkeypatch):
    from app.services.discovery import discover
    judged = []
    monkeypatch.setattr(fit, "complete_json", lambda rt, kind, system, payload, max_tokens=4096:
                        judged.append(payload) or {"people": []})
    fit.judge(ai, discover(ai, "robotics"))
    assert "seed_profile" not in judged[0]


def test_seed_description_is_one_logged_model_call(ai, monkeypatch):
    import httpx
    from app.integrations import llm
    monkeypatch.setattr(llm.httpx, "post", lambda url, **kwargs: httpx.Response(200, json={
        "candidates": [{"content": {"parts": [{"text": '{"summary": "Robotics.", "topics": ["robotics"]}'}]}}],
        "usageMetadata": {"promptTokenCount": 9, "candidatesTokenCount": 4}}))
    seed_search(ai, "ada_robotics")
    with ai.factory() as db:
        assert [c.kind for c in db.scalars(select(AICall))] == ["seed"]


def test_migration_0003_is_safe_to_repeat(database):
    engine, _, _ = database
    path = Path(__file__).resolve().parent.parent / "migrations" / "versions" / "0003_seed_accounts.py"
    spec = importlib.util.spec_from_file_location("migration_0003", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert (migration.revision, migration.down_revision) == ("0003", "0002")
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE search_runs DROP COLUMN IF EXISTS seed_handles"))
        connection.execute(text("ALTER TABLE search_runs DROP COLUMN IF EXISTS seed_summary"))
    for _ in range(2):
        with engine.begin() as connection:
            migration.apply(connection)
    assert {"seed_handles", "seed_summary"} <= {c["name"] for c in inspect(engine).get_columns("search_runs")}
