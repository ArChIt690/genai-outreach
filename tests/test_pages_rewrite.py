from app.services import drafting
from test_pages import client, drafted, judged_search, outreach, post  # noqa: F401  (client is a fixture)

NEW_TEXT = "Hi Ada, your grasp recovery tests caught my eye. Open to a short chat? Reply STOP to opt out."


def fake_model(monkeypatch):
    asked = []

    def fake(rt, kind, system, payload, max_tokens=4096, strong=False):
        asked.append((kind, strong, payload.get("reviewer_note")))
        source_id, post_text = next(iter(payload["sources"].items()))
        return {"draft_text": NEW_TEXT, "claims": [{"source_id": source_id, "quote": post_text[:20]}],
                "uncertainties": []}
    monkeypatch.setattr(drafting, "complete_json", fake)
    return asked


def test_rewrite_button_appears_only_when_ai_is_on(client, rt):  # noqa: F811
    judged_search(rt)
    oid = drafted(rt)
    assert f'action="/outreach/{oid}/rewrite"' not in client.get("/review").text
    rt.settings.draft_provider, rt.settings.openai_api_key = "openai", "test-openai-key"
    page = client.get("/review").text
    assert f'action="/outreach/{oid}/rewrite"' in page and "Rewrite with gpt-6.1-terra" in page


def test_rewrite_action_replaces_the_draft_and_returns_to_review(client, rt, monkeypatch):  # noqa: F811
    rt.settings.draft_provider, rt.settings.openai_api_key = "openai", "test-openai-key"
    asked = fake_model(monkeypatch)
    judged_search(rt)
    oid = drafted(rt)
    asked.clear()
    response = post(client, f"/outreach/{oid}/rewrite", version="1", next="review", note="shorter")
    assert response.status_code == 303 and response.headers["location"].startswith("/review?notice=")
    assert asked == [("rewrite", True, "shorter")]
    assert outreach(rt, oid).draft == NEW_TEXT
    page = client.get(response.headers["location"]).text
    assert "Rewritten." in page and "AI draft · gpt-6.1-terra" in page


def test_rewrite_action_requires_csrf_and_reports_when_ai_is_off(client, rt):  # noqa: F811
    judged_search(rt)
    oid = drafted(rt)
    before = outreach(rt, oid).draft
    assert client.post(f"/outreach/{oid}/rewrite", data={"version": "1"}).status_code == 403
    response = post(client, f"/outreach/{oid}/rewrite", version="1", next="review")
    assert response.status_code == 409 and "AI_NOT_CONFIGURED" in response.text
    assert outreach(rt, oid).draft == before
