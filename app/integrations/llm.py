"""One entry point for every model request.

Callers pass public text only (profiles, posts, sender name, purpose). Each request is
recorded in ai_calls. Error text is written here; provider response bodies are never kept.
"""
import json
import time

import httpx
from sqlalchemy import func, select

from app.models import AICall, now
from app.services.usage import reserve

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
OPENAI_URL = "https://api.openai.com/v1/responses"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
# Reasoning tokens count against the output limit, so OpenAI requests get at least this much room.
OPENAI_MIN_OUTPUT_TOKENS = 8192
BUSY_STATUSES = {429, 500, 502, 503, 504}


class LLMError(Exception):
    """code is shown to callers; detail is an application-authored note for the call log."""
    def __init__(self, code, detail=None):
        self.code, self.detail = code, detail or code
        super().__init__(code)


class _Busy(Exception):
    def __init__(self, detail):
        self.detail = detail
        super().__init__(detail)


def ai_ready(settings) -> bool:
    if settings.draft_provider == "gemini":
        return bool(settings.gemini_api_key)
    if settings.draft_provider == "openai":
        return bool(settings.openai_api_key)
    if settings.draft_provider == "anthropic":
        return bool(settings.anthropic_api_key and settings.anthropic_model
                    and settings.model_data_use_acknowledged and settings.app_mode == "live")
    return False


def provider_label(settings) -> str:
    return settings.draft_provider if ai_ready(settings) else "evidence template"


def model_name(settings) -> str:
    if settings.draft_provider == "gemini":
        return settings.gemini_model
    if settings.draft_provider == "openai":
        return settings.openai_model
    if settings.draft_provider == "anthropic":
        return settings.anthropic_model
    return ""


def strong_model_name(settings) -> str:
    """The model used when a person asks for a rewrite. Only OpenAI has a separate stronger model."""
    if settings.draft_provider == "openai" and settings.openai_strong_model:
        return settings.openai_strong_model
    return model_name(settings)


def _parse(text):
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    try:
        data = json.loads(text)
    except ValueError:
        raise LLMError("AI_BAD_RESPONSE") from None
    if not isinstance(data, dict):
        raise LLMError("AI_BAD_RESPONSE")
    return data


def _gemini(settings, model, system, payload, max_tokens):
    try:
        response = httpx.post(GEMINI_URL.format(model=model), headers={
            "x-goog-api-key": settings.gemini_api_key,
        }, json={
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": json.dumps(payload)}]}],
            "generationConfig": {"responseMimeType": "application/json", "maxOutputTokens": max_tokens,
                                 "temperature": 0.4},
        }, timeout=30, follow_redirects=False)
    except httpx.HTTPError:
        raise _Busy("NETWORK") from None
    if response.status_code in BUSY_STATUSES:
        raise _Busy(f"HTTP_{response.status_code}")
    if response.status_code != 200:
        raise LLMError("AI_UNAVAILABLE", f"HTTP_{response.status_code}")
    try:
        body = response.json()
        candidates = body.get("candidates") or []
        parts = (candidates[0].get("content") or {}).get("parts") or [] if candidates else []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        usage = body.get("usageMetadata") or {}
        tokens = (usage.get("promptTokenCount"), usage.get("candidatesTokenCount"))
    except (ValueError, AttributeError, TypeError):
        raise LLMError("AI_BAD_RESPONSE") from None
    try:
        return _parse(text), tokens
    except LLMError as exc:
        exc.tokens = tokens
        raise


def _openai(settings, model, system, payload, max_tokens):
    try:
        response = httpx.post(OPENAI_URL, headers={
            "Authorization": "Bearer " + settings.openai_api_key,
        }, json={
            "model": model, "instructions": system, "input": json.dumps(payload),
            "text": {"format": {"type": "json_object"}},
            "max_output_tokens": max(max_tokens, OPENAI_MIN_OUTPUT_TOKENS),
        }, timeout=60, follow_redirects=False)
    except httpx.HTTPError:
        raise _Busy("NETWORK") from None
    if response.status_code in BUSY_STATUSES:
        raise _Busy(f"HTTP_{response.status_code}")
    if response.status_code != 200:
        raise LLMError("AI_UNAVAILABLE", f"HTTP_{response.status_code}")
    try:
        body = response.json()
        usage = body.get("usage") or {}
        tokens = (usage.get("input_tokens"), usage.get("output_tokens"))
        complete = body.get("status") == "completed"
        text = "".join(part.get("text", "") for item in body.get("output") or []
                       if item.get("type") == "message"
                       for part in item.get("content") or [] if part.get("type") == "output_text")
    except (ValueError, AttributeError, TypeError):
        raise LLMError("AI_BAD_RESPONSE") from None
    try:
        if not complete:
            # Usually the output limit was reached before any text was written.
            raise LLMError("AI_BAD_RESPONSE", "AI_INCOMPLETE")
        return _parse(text), tokens
    except LLMError as exc:
        exc.tokens = tokens
        raise


def _anthropic(settings, system, payload, max_tokens):
    # Untested against the real service.
    try:
        response = httpx.post(ANTHROPIC_URL, headers={
            "x-api-key": settings.anthropic_api_key, "anthropic-version": "2026-10-21",
        }, json={
            "model": settings.anthropic_model, "max_tokens": min(max_tokens, 600), "system": system,
            "messages": [{"role": "user", "content": json.dumps(payload)}],
        }, timeout=20, follow_redirects=False)
        response.raise_for_status()
        body = response.json()
        text = "".join(c["text"] for c in body["content"] if c.get("type") == "text")
        usage = body.get("usage") or {}
    except httpx.HTTPError:
        raise LLMError("AI_UNAVAILABLE", "NETWORK_OR_HTTP") from None
    except (ValueError, KeyError, TypeError, AttributeError):
        raise LLMError("AI_BAD_RESPONSE") from None
    return _parse(text), (usage.get("input_tokens"), usage.get("output_tokens"))


def _record(rt, kind, provider, model, tokens, started, outcome, error):
    with rt.factory.begin() as db:
        db.add(AICall(kind=kind[:40], provider=provider, model=(model or "")[:80],
                      input_tokens=tokens[0] if isinstance(tokens[0], int) else None,
                      output_tokens=tokens[1] if isinstance(tokens[1], int) else None,
                      latency_ms=round((time.monotonic() - started) * 1000),
                      outcome=outcome, error=error[:80] if error else None))


def complete_json(rt, kind: str, system: str, payload: dict, max_tokens: int = 4096,
                  strong: bool = False) -> dict:
    """Ask the configured model for one JSON object. Raises LLMError; writes one ai_calls row
    for every request that reaches the network. strong=True asks the stronger model directly,
    where the provider has one."""
    settings = rt.settings
    if not ai_ready(settings):
        raise LLMError("AI_NOT_CONFIGURED")
    midnight = now().replace(hour=0, minute=0, second=0, microsecond=0)
    with rt.factory() as db:
        used = db.scalar(select(func.count()).select_from(AICall).where(AICall.created >= midnight))
    if used >= settings.ai_daily_call_limit:
        raise LLMError("AI_DAILY_LIMIT")
    provider = settings.draft_provider
    if provider == "anthropic":
        # USD 0.10 conservative reservation, not a billing guarantee for arbitrary models.
        reserve(rt.factory, settings, "model_draft", 100_000, model=True)
        models = [settings.anthropic_model]
    elif provider == "openai":
        models = [strong_model_name(settings)] if strong else [settings.openai_model]
        if not strong and settings.openai_strong_model and settings.openai_strong_model != settings.openai_model:
            models.append(settings.openai_strong_model)
    else:
        models = [settings.gemini_model]
        if settings.gemini_fallback_model and settings.gemini_fallback_model != settings.gemini_model:
            models.append(settings.gemini_fallback_model)
    started = time.monotonic()
    outcome, error, model, tokens = "failed", None, models[0], (None, None)
    try:
        for index, model in enumerate(models):
            try:
                if provider == "anthropic":
                    data, tokens = _anthropic(settings, system, payload, max_tokens)
                elif provider == "openai":
                    data, tokens = _openai(settings, model, system, payload, max_tokens)
                else:
                    data, tokens = _gemini(settings, model, system, payload, max_tokens)
            except _Busy as busy:
                error = busy.detail
                continue
            outcome = "ok" if index == 0 else "fallback_model"
            return data
        raise LLMError("AI_UNAVAILABLE", error)
    except LLMError as exc:
        error, tokens = exc.detail, getattr(exc, "tokens", tokens)
        raise
    finally:
        _record(rt, kind, provider, model, tokens, started, outcome, error)
