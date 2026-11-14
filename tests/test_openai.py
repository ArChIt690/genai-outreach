"""OpenAI adapter, tested against a fake server. No request leaves the machine."""
import json

import httpx
import pytest
from sqlalchemy import select

from app.config import Settings
from app.integrations import llm
from app.integrations.llm import LLMError, ai_ready, complete_json, model_name, provider_label
from app.models import AICall


def openai_reply(text='{"a": 1}', status=200, body=None):
    if body is None:
        body = {"status": "completed", "output": [
            {"type": "reasoning", "summary": []},
            {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]},
        ], "usage": {"input_tokens": 40, "output_tokens": 300,
                     "output_tokens_details": {"reasoning_tokens": 250}}}
    return httpx.Response(status, json=body)


class FakePost:
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


@pytest.fixture
def openai(rt):
    rt.settings.draft_provider = "openai"
    rt.settings.openai_api_key = "test-openai-key"
    return rt


def use(monkeypatch, *replies):
    fake = FakePost(*replies)
    monkeypatch.setattr(llm.httpx, "post", fake)
    return fake


def calls(rt):
    with rt.factory() as db:
        return db.scalars(select(AICall).order_by(AICall.created)).all()


def test_openai_settings_defaults():
    s = Settings(_env_file=None)
    assert (s.openai_model, s.openai_strong_model, s.openai_api_key) == ("gpt-6-luna", "gpt-6.1-terra", "")
    assert Settings(_env_file=None, draft_provider="openai").draft_provider == "openai"


def test_openai_needs_a_key(rt):
    rt.settings.draft_provider = "openai"
    assert not ai_ready(rt.settings) and provider_label(rt.settings) == "evidence template"
    rt.settings.openai_api_key = "test-openai-key"
    assert ai_ready(rt.settings) and provider_label(rt.settings) == "openai"
    assert model_name(rt.settings) == "gpt-6-luna"


def test_openai_success_uses_luna_and_is_logged(openai, monkeypatch):
    fake = use(monkeypatch, openai_reply())
    assert complete_json(openai, "fit", "Return JSON.", {"q": "hello"}) == {"a": 1}
    [(url, kwargs)] = fake.calls
    assert url == "https://api.openai.com/v1/responses"
    assert kwargs["headers"]["Authorization"] == "Bearer test-openai-key"
    body = kwargs["json"]
    assert body["model"] == "gpt-6-luna" and body["instructions"] == "Return JSON."
    assert json.loads(body["input"]) == {"q": "hello"}
    assert body["text"] == {"format": {"type": "json_object"}}
    assert body["max_output_tokens"] >= 8192
    assert "test-openai-key" not in json.dumps(body)
    [row] = calls(openai)
    assert (row.provider, row.model, row.outcome) == ("openai", "gpt-6-luna", "ok")
    assert (row.input_tokens, row.output_tokens) == (40, 300)


def test_busy_luna_falls_back_to_terra(openai, monkeypatch):
    fake = use(monkeypatch, openai_reply(status=429, body={}), openai_reply())
    assert complete_json(openai, "draft", "JSON", {}) == {"a": 1}
    assert [c[1]["json"]["model"] for c in fake.calls] == ["gpt-6-luna", "gpt-6.1-terra"]
    [row] = calls(openai)
    assert (row.model, row.outcome) == ("gpt-6.1-terra", "fallback_model")


def test_strong_request_goes_straight_to_terra(openai, monkeypatch):
    fake = use(monkeypatch, openai_reply())
    complete_json(openai, "rewrite", "JSON", {}, strong=True)
    assert [c[1]["json"]["model"] for c in fake.calls] == ["gpt-6.1-terra"]
    [row] = calls(openai)
    assert (row.model, row.outcome) == ("gpt-6.1-terra", "ok")


def test_strong_request_has_no_second_try(openai, monkeypatch):
    fake = use(monkeypatch, openai_reply(status=503, body={}))
    with pytest.raises(LLMError) as e:
        complete_json(openai, "rewrite", "JSON", {}, strong=True)
    assert e.value.code == "AI_UNAVAILABLE" and len(fake.calls) == 1


def test_strong_is_ignored_for_gemini(rt, monkeypatch):
    rt.settings.draft_provider, rt.settings.gemini_api_key = "gemini", "test-key"
    fake = use(monkeypatch, httpx.Response(200, json={
        "candidates": [{"content": {"parts": [{"text": '{"a": 1}'}]}}], "usageMetadata": {}}))
    complete_json(rt, "rewrite", "JSON", {}, strong=True)
    assert "gemini-2.5-flash" in fake.calls[0][0]


def test_answer_cut_off_by_the_token_limit_is_a_bad_response(openai, monkeypatch):
    cut = {"status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"},
           "output": [{"type": "reasoning", "summary": []}],
           "usage": {"input_tokens": 40, "output_tokens": 8192}}
    fake = use(monkeypatch, openai_reply(body=cut))
    with pytest.raises(LLMError) as e:
        complete_json(openai, "fit", "JSON", {})
    assert e.value.code == "AI_BAD_RESPONSE" and len(fake.calls) == 1
    [row] = calls(openai)
    assert (row.outcome, row.error, row.output_tokens) == ("failed", "AI_INCOMPLETE", 8192)


def test_refusal_is_a_bad_response(openai, monkeypatch):
    refused = {"status": "completed", "output": [{"type": "message", "content": [
        {"type": "refusal", "refusal": "I can't help with that."}]}], "usage": {}}
    use(monkeypatch, openai_reply(body=refused))
    with pytest.raises(LLMError) as e:
        complete_json(openai, "fit", "JSON", {})
    assert e.value.code == "AI_BAD_RESPONSE"


def test_wrong_key_is_unavailable_without_fallback_and_body_is_not_kept(openai, monkeypatch):
    fake = use(monkeypatch, openai_reply(status=401, body={"error": {"message": "SECRET test-openai-key"}}))
    with pytest.raises(LLMError) as e:
        complete_json(openai, "fit", "JSON", {})
    assert e.value.code == "AI_UNAVAILABLE" and len(fake.calls) == 1
    [row] = calls(openai)
    assert row.error == "HTTP_401" and "SECRET" not in str(e.value)


def test_network_error_on_luna_falls_back(openai, monkeypatch):
    fake = use(monkeypatch, httpx.ConnectError("redacted"), openai_reply())
    assert complete_json(openai, "fit", "JSON", {}) == {"a": 1}
    assert len(fake.calls) == 2
