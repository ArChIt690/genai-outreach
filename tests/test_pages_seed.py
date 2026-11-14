import re

from app.services import fit, seeds
from test_pages import client, post  # noqa: F401  (client is a fixture)

PROFILE = {"summary": "Builds open robotics manipulation benchmarks.", "topics": ["robotics"]}


def ai_on(rt, monkeypatch):
    rt.settings.draft_provider, rt.settings.gemini_api_key = "gemini", "test-key"
    monkeypatch.setattr(seeds, "complete_json", lambda *args, **kwargs: PROFILE)
    monkeypatch.setattr(fit, "complete_json", lambda *args, **kwargs: {"people": [{
        "candidate_id": "fixture_mira", "fit": "strong", "role": "researcher",
        "reason": "Runs robotics experiments like the seed.",
        "quotes": [{"source_id": "p_mira", "quote": "Our robotics experiments"}]}]})


def test_seed_form_is_disabled_until_ai_is_on(client, rt):  # noqa: F811
    page = client.get("/discover").text
    assert 'action="/searches/seed"' in page
    assert re.search(r"<button[^>]*disabled[^>]*>Find similar people", page)
    rt.settings.draft_provider, rt.settings.gemini_api_key = "gemini", "test-key"
    assert not re.search(r"<button[^>]*disabled[^>]*>Find similar people", client.get("/discover").text)


def test_seed_search_action_shows_what_it_started_from(client, rt, monkeypatch):  # noqa: F811
    ai_on(rt, monkeypatch)
    response = post(client, "/searches/seed", handles="@ada_robotics")
    assert response.status_code == 303 and response.headers["location"].startswith("/discover?run=")
    page = client.get(response.headers["location"]).text
    assert "Started from @ada_robotics" in page and PROFILE["summary"] in page
    assert "Mira Nguyen" in page and "Runs robotics experiments like the seed." in page
    assert '<a href="/candidates/fixture_ada">' not in page


def test_seed_search_action_errors(client, rt, monkeypatch):  # noqa: F811
    assert client.post("/searches/seed", data={"handles": "ada_robotics"}).status_code == 403
    without_ai = post(client, "/searches/seed", handles="ada_robotics")
    assert without_ai.status_code == 409 and "AI_NOT_CONFIGURED" in without_ai.text
    ai_on(rt, monkeypatch)
    assert post(client, "/searches/seed", handles="not a handle!").status_code == 400
    missing = post(client, "/searches/seed", handles="nobody_here")
    assert missing.status_code == 404 and "SEED_NOT_FOUND" in missing.text
