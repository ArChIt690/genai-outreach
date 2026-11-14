from typing import Literal
from urllib.parse import urlsplit

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_mode: Literal["fixture", "live"] = "fixture"
    app_origin: str = "http://127.0.0.1:8000"
    database_url: str = "postgresql+psycopg://outreach:outreach@127.0.0.1:5432/outreach"
    operator_password_hash: str = ""
    token_encryption_key: str = ""
    send_enabled: bool = False
    x_client_id: str = ""
    x_client_secret: str = ""
    x_callback_url: str = "http://127.0.0.1:8000/oauth/x/callback"
    test_recipient_ids: str = ""
    history_limit_acknowledged: bool = False
    x_budget_usd: float = 5
    model_budget_usd: float = 1
    daily_send_limit: int = 10
    send_min_gap_seconds: int = 120
    queue_tick_seconds: int = 30
    auto_sync_minutes: int = 180
    worker_enabled: bool = True
    outreach_policy: Literal["test_allowlist", "operator_approved"] = "test_allowlist"
    draft_provider: Literal["template", "gemini", "openai", "anthropic"] = "template"
    draft_limit_per_session: int = 40
    ai_daily_call_limit: int = 200
    openai_api_key: str = ""
    openai_model: str = "gpt-6-luna"
    openai_strong_model: str = "gpt-6.1-terra"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_fallback_model: str = "gemini-flash-lite-latest"
    anthropic_api_key: str = ""
    anthropic_model: str = ""
    model_data_use_acknowledged: bool = False
    session_hours: int = 8
    stale_send_seconds: int = 120
    evidence_max_age_seconds: int = 3600

    @model_validator(mode="after")
    def validate_deployment(self):
        origin = urlsplit(self.app_origin)
        if origin.scheme not in {"http", "https"} or not origin.hostname or origin.path:
            raise ValueError("APP_ORIGIN must be an origin without a path")
        if origin.scheme != "https" and origin.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Non-loopback deployments require HTTPS")
        if not self.database_url.startswith("postgresql+psycopg://"):
            raise ValueError("PostgreSQL with psycopg is required")
        if self.app_mode == "live" and self.x_callback_url != self.app_origin + "/oauth/x/callback":
            raise ValueError("X_CALLBACK_URL must match APP_ORIGIN/oauth/x/callback")
        return self

    @property
    def allowed_ids(self) -> set[str]:
        return {x.strip() for x in self.test_recipient_ids.split(",") if x.strip()}

    @property
    def secure_cookie(self) -> bool:
        return self.app_origin.startswith("https://")
