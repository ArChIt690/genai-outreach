from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, false
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now():
    return datetime.now(UTC)


def uid():
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default="main")
    mode: Mapped[str] = mapped_column(String(12))
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    sender_name: Mapped[str] = mapped_column(String(100), default="Prototype operator")
    purpose: Mapped[str] = mapped_column(Text, default="I'd like to learn about your current AI or robotics work.")
    purpose_version: Mapped[int] = mapped_column(Integer, default=1)
    spend_micros: Mapped[int] = mapped_column(Integer, default=0)
    model_spend_micros: Mapped[int] = mapped_column(Integer, default=0)
    history_acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)


class OperatorSession(Base):
    __tablename__ = "operator_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    csrf: Mapped[str] = mapped_column(String(80))
    expires: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    oauth_state_hash: Mapped[str | None] = mapped_column(String(64))
    oauth_verifier: Mapped[str | None] = mapped_column(Text)
    oauth_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    draft_count: Mapped[int] = mapped_column(Integer, default=0)


class Account(Base):
    __tablename__ = "accounts"
    x_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    handle: Mapped[str] = mapped_column(String(100))
    token: Mapped[str | None] = mapped_column(Text)
    refresh: Mapped[str | None] = mapped_column(Text)
    expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scopes: Mapped[str] = mapped_column(Text, default="")
    connected: Mapped[bool] = mapped_column(Boolean, default=True)
    active_attempt: Mapped[str | None] = mapped_column(String(40))
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refresh_claim: Mapped[str | None] = mapped_column(String(40))
    refresh_claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SearchRun(Base):
    __tablename__ = "search_runs"
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=uid)
    query: Mapped[str] = mapped_column(Text)
    terms: Mapped[list] = mapped_column(JSON)
    count: Mapped[int] = mapped_column(Integer, default=0)
    capped: Mapped[bool] = mapped_column(Boolean, default=False)
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    seed_handles: Mapped[list | None] = mapped_column(JSON)
    seed_summary: Mapped[str | None] = mapped_column(Text)


class Candidate(Base):
    __tablename__ = "candidates"
    x_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    handle: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(150))
    bio: Mapped[str] = mapped_column(Text, default="")
    location: Mapped[str] = mapped_column(String(200), default="")
    manual: Mapped[bool] = mapped_column(Boolean, default=False)
    available: Mapped[bool] = mapped_column(Boolean, default=True)


class SearchResult(Base):
    __tablename__ = "search_results"
    __table_args__ = (UniqueConstraint("run_id", "candidate_id"),)
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=uid)
    run_id: Mapped[str] = mapped_column(ForeignKey("search_runs.id"))
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.x_id"))
    score: Mapped[int] = mapped_column(Integer)
    reasons: Mapped[list] = mapped_column(JSON)
    ai_fit: Mapped[str | None] = mapped_column(String(12))
    ai_role: Mapped[str | None] = mapped_column(String(20))
    ai_reason: Mapped[str | None] = mapped_column(Text)
    ai_quotes: Mapped[list | None] = mapped_column(JSON)


class Evidence(Base):
    __tablename__ = "evidence"
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.x_id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    retrieved: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    published: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    available: Mapped[bool] = mapped_column(Boolean, default=True)


class Consent(Base):
    __tablename__ = "consents"
    __table_args__ = (UniqueConstraint("sender_id", "recipient_id"),)
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=uid)
    sender_id: Mapped[str] = mapped_column(ForeignKey("accounts.x_id"))
    recipient_id: Mapped[str] = mapped_column(ForeignKey("candidates.x_id"))
    reference: Mapped[str] = mapped_column(Text)
    controlled: Mapped[bool] = mapped_column(Boolean)
    version: Mapped[int] = mapped_column(Integer, default=1)
    purpose_version: Mapped[int] = mapped_column(Integer)
    expires: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class Outreach(Base):
    __tablename__ = "outreach"
    __table_args__ = (UniqueConstraint("sender_id", "recipient_id"),)
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=uid)
    sender_id: Mapped[str] = mapped_column(ForeignKey("accounts.x_id"))
    recipient_id: Mapped[str] = mapped_column(ForeignKey("candidates.x_id"))
    draft: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=0)
    approved_hash: Mapped[str | None] = mapped_column(String(64))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approval_snapshot: Mapped[dict | None] = mapped_column(JSON)
    draft_meta: Mapped[dict] = mapped_column(JSON, default=dict)
    selected_sources: Mapped[list] = mapped_column(JSON, default=list)
    test_message: Mapped[bool] = mapped_column(Boolean, default=False)
    send_status: Mapped[str] = mapped_column(String(30), default="not_sent")
    conversation_id: Mapped[str | None] = mapped_column(String(100))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sync_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    sync_error: Mapped[str | None] = mapped_column(String(80))
    skipped: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    queue_key: Mapped[str | None] = mapped_column(String(80))
    queue_note: Mapped[str | None] = mapped_column(String(80))


class Attempt(Base):
    __tablename__ = "send_attempts"
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=uid)
    request_key: Mapped[str] = mapped_column(String(80), unique=True)
    outreach_id: Mapped[str] = mapped_column(ForeignKey("outreach.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    payload_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30), default="in_flight")
    started: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    finished: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    external_id: Mapped[str | None] = mapped_column(String(80))
    error: Mapped[str | None] = mapped_column(String(80))


class DMEvent(Base):
    __tablename__ = "dm_events"
    __table_args__ = (UniqueConstraint("account_id", "external_id"),)
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=uid)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.x_id"))
    recipient_id: Mapped[str] = mapped_column(ForeignKey("candidates.x_id"), index=True)
    external_id: Mapped[str] = mapped_column(String(80))
    conversation_id: Mapped[str] = mapped_column(String(100))
    sender_id: Mapped[str] = mapped_column(String(40))
    text: Mapped[str] = mapped_column(Text)
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Suppression(Base):
    __tablename__ = "suppressions"
    recipient_id: Mapped[str] = mapped_column(ForeignKey("candidates.x_id"), primary_key=True)
    reason: Mapped[str] = mapped_column(Text)
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Usage(Base):
    __tablename__ = "usage"
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=uid)
    kind: Mapped[str] = mapped_column(String(40))
    reserved_micros: Mapped[int] = mapped_column(Integer)
    settled_micros: Mapped[int | None] = mapped_column(Integer)
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Audit(Base):
    __tablename__ = "audit"
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=uid)
    action: Mapped[str] = mapped_column(String(80))
    subject: Mapped[str] = mapped_column(String(80))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AICall(Base):
    """One row per model request: what it was for, what it cost in tokens, how it ended."""
    __tablename__ = "ai_calls"
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=uid)
    kind: Mapped[str] = mapped_column(String(40))
    provider: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(80))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    outcome: Mapped[str] = mapped_column(String(20))
    error: Mapped[str | None] = mapped_column(String(80))
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


class FixtureMessage(Base):
    """Synthetic provider state persists independently of application DM imports."""
    __tablename__ = "fixture_messages"
    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=uid)
    recipient_id: Mapped[str] = mapped_column(String(40))
    sender_id: Mapped[str] = mapped_column(String(40))
    text: Mapped[str] = mapped_column(Text)
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
