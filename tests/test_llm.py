import json

import httpx
import pytest
from sqlalchemy import select

from app.integrations import llm
from app.integrations.llm import LLMError, ai_ready, complete_json, provider_label
from app.models import AICall


def gemini_reply(text='{"a": 1}', status=200, body=None):
    if body is None:
        body = {"candidates": [{"content": {"parts": [{"text": text}]}}],
                "usageMetadata": {"promptTokenCount": 12, "candidatesTokenCount": 5}}
    return httpx.Response(status, json=body)


class FakePost:
    """Stands in for httpx.post and replays the given responses in order."""
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


@pytest.fixture
def gemini(rt):
    rt.settings.draft_provider = "gemini"
    rt.settings.gemini_api_key = "test-key"
    return rt


def use(monkeypatch, *replies):
    fake = FakePost(*replies)
    monkeypatch.setattr(llm.httpx, "post", fake)
    return fake


def calls(rt):
    with rt.factory() as db:
        return db.scalars(select(AICall)).all()


def test_gemini_success_is_logged(gemini, monkeypatch):
    fake = use(monkeypatch, gemini_reply())
    assert complete_json(gemini, "fit", "system text", {"q": "hello"}) == {"a": 1}
    url, kwargs = fake.calls[0]
    assert "gemini-2.5-flash" in url and "test-key" not in url
    assert kwargs["headers"]["x-goog-api-key"] == "test-key"
    assert kwargs["json"]["generationConfig"]["responseMimeType"] == "application/json"
    assert kwargs["json"]["systemInstruction"]["parts"][0]["text"] == "system text"
    assert json.loads(kwargs["json"]["contents"][0]["parts"][0]["text"]) == {"q": "hello"}
    [row] = calls(gemini)
    assert (row.kind, row.provider, row.model, row.outcome) == ("fit", "gemini", "gemini-2.5-flash", "ok")
    assert (row.input_tokens, row.output_tokens, row.error) == (12, 5, None)


def test_busy_model_uses_fallback(gemini, monkeypatch):
    fake = use(monkeypatch, gemini_reply(status=503, body={"error": "busy"}), gemini_reply())
    assert complete_json(gemini, "draft", "s", {}) == {"a": 1}
    assert len(fake.calls) == 2 and "gemini-flash-lite-latest" in fake.calls[1][0]
    [row] = calls(gemini)
    assert (row.outcome, row.model) == ("fallback_model", "gemini-flash-lite-latest")


def test_network_error_uses_fallback(gemini, monkeypatch):
    fake = use(monkeypatch, httpx.ConnectError("redacted"), gemini_reply())
    assert complete_json(gemini, "draft", "s", {}) == {"a": 1}
    assert len(fake.calls) == 2


def test_both_models_failing_raises(gemini, monkeypatch):
    use(monkeypatch, gemini_reply(status=503, body={}), gemini_reply(status=429, body={}))
    with pytest.raises(LLMError) as e:
        complete_json(gemini, "fit", "s", {})
    assert e.value.code == "AI_UNAVAILABLE"
    [row] = calls(gemini)
    assert row.outcome == "failed"


def test_fenced_json_is_parsed(gemini, monkeypatch):
    use(monkeypatch, gemini_reply(text='```json\n{"a": 1}\n```'))
    assert complete_json(gemini, "fit", "s", {}) == {"a": 1}


def test_no_candidates_is_bad_response(gemini, monkeypatch):
    fake = use(monkeypatch, gemini_reply(body={"candidates": []}))
    with pytest.raises(LLMError) as e:
        complete_json(gemini, "fit", "s", {})
    assert e.value.code == "AI_BAD_RESPONSE" and len(fake.calls) == 1
    [row] = calls(gemini)
    assert (row.outcome, row.error) == ("failed", "AI_BAD_RESPONSE")


@pytest.mark.parametrize("text", ["not json at all", "[1, 2]", ""])
def test_text_that_is_not_a_json_object_is_bad_response(gemini, monkeypatch, text):
    use(monkeypatch, gemini_reply(text=text))
    with pytest.raises(LLMError) as e:
        complete_json(gemini, "fit", "s", {})
    assert e.value.code == "AI_BAD_RESPONSE"


def test_template_provider_makes_no_call(rt, monkeypatch):
    fake = use(monkeypatch)
    with pytest.raises(LLMError) as e:
        complete_json(rt, "fit", "s", {})
    assert e.value.code == "AI_NOT_CONFIGURED" and fake.calls == []
    assert not ai_ready(rt.settings) and provider_label(rt.settings) == "evidence template"


def test_gemini_without_key_is_not_ready(rt):
    rt.settings.draft_provider = "gemini"
    assert not ai_ready(rt.settings)
    rt.settings.gemini_api_key = "test-key"
    assert ai_ready(rt.settings) and provider_label(rt.settings) == "gemini"


def test_daily_limit_blocks_without_network(gemini, monkeypatch):
    gemini.settings.ai_daily_call_limit = 1
    fake = use(monkeypatch, gemini_reply(), gemini_reply())
    complete_json(gemini, "fit", "s", {})
    with pytest.raises(LLMError) as e:
        complete_json(gemini, "fit", "s", {})
    assert e.value.code == "AI_DAILY_LIMIT" and len(fake.calls) == 1


def test_error_text_never_contains_provider_body(gemini, monkeypatch):
    fake = use(monkeypatch, gemini_reply(status=400, body={"error": {"message": "SECRET test-key"}}))
    with pytest.raises(LLMError) as e:
        complete_json(gemini, "fit", "s", {})
    assert e.value.code == "AI_UNAVAILABLE" and len(fake.calls) == 1
    [row] = calls(gemini)
    assert "SECRET" not in str(e.value) and "SECRET" not in row.error and "test-key" not in row.error
