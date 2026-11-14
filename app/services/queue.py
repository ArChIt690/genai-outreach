"""Paced send queue.

The queue only decides WHEN to call the existing send(); every safety check in send() still
runs. Each queued message carries one stored request key, so a restart replays the stored
result instead of dispatching a second message.
"""
import logging
import secrets
import threading
import time
from datetime import timedelta

from sqlalchemy import func, or_, select

from app.errors import DomainError, ProviderError
from app.models import Account, Attempt, Audit, Candidate, Outreach, SearchResult, SearchRun, Workspace, now
from app.services.fit import fit_rank
from app.services.outreach import approve, eligibility, locked_rows
from app.services.sending import send
from app.services.synchronization import recover_stale, sync

log = logging.getLogger("outreach.worker")

# Conditions that are about the workspace or the moment, not about one person: the message waits.
HOLD_CODES = {"SENDING_PAUSED", "SENDING_DISABLED", "RATE_LIMITED", "HISTORY_ACKNOWLEDGEMENT_REQUIRED",
              "ACCOUNT_RECONNECT_REQUIRED", "SENDER_BUSY", "DAILY_LIMIT", "BUDGET_EXCEEDED",
              "HISTORY_INCOMPLETE", "TOKEN_REFRESH_BUSY", "X_UNAVAILABLE"}
# Holds that may be specific to one conversation: let the next message go first.
ROTATE_CODES = {"HISTORY_INCOMPLETE", "X_UNAVAILABLE"}
# Holds that cost a network call to discover: the worker waits longer before trying again.
BACKOFF_CODES = {"HISTORY_INCOMPLETE", "X_UNAVAILABLE", "TOKEN_REFRESH_BUSY", "BUDGET_EXCEEDED",
                 "ACCOUNT_RECONNECT_REQUIRED"}
BACKOFF_SECONDS = 300
# Replies are checked automatically for this long after a send; "Sync all now" has no such limit.
SYNC_WINDOW_DAYS = 14


def _refuse_blocked(reasons):
    blocking = [r for r in reasons if r not in HOLD_CODES]
    if blocking:
        raise DomainError(blocking[0], "This message cannot be queued: " + ", ".join(blocking))


def enqueue(rt, oid: str, expected: int) -> None:
    """Approve this exact version and put it in the send queue."""
    with rt.factory.begin() as db:
        w, a, o = locked_rows(db, oid)
        _refuse_blocked(eligibility(db, rt.settings, w, a, o, require_approval=False))
    approve(rt, oid, expected)
    with rt.factory.begin() as db:
        w, a, o = locked_rows(db, oid)
        if o.version != expected:
            raise DomainError("APPROVAL_STALE", "This draft changed in another tab. Refresh and review it.")
        _refuse_blocked(eligibility(db, rt.settings, w, a, o))
        if not o.queued_at:
            o.queued_at, o.queue_key = now(), secrets.token_urlsafe(24)
        o.queue_note, o.skipped = None, False
        db.add(Audit(action="message_queued", subject=oid, details={"version": o.version}))


def unqueue(rt, oid: str) -> None:
    """Take a message out of the queue. It needs a fresh approval before it can go again."""
    with rt.factory.begin() as db:
        _, _, o = locked_rows(db, oid)
        if o.queued_at and o.send_status in {"not_sent", "rejected"}:
            o.approved_hash, o.approved_at, o.approval_snapshot = None, None, None
        o.queued_at, o.queue_key = None, None
        db.add(Audit(action="message_unqueued", subject=oid))


def skip(rt, oid: str) -> None:
    """Hide a draft from review without blocking the person. A newly saved draft brings it back."""
    with rt.factory.begin() as db:
        _, _, o = locked_rows(db, oid)
        if o.send_status != "not_sent":
            raise DomainError("ALREADY_CONTACTED", "This message is already sent, in progress, or unresolved.")
        o.skipped = True
        o.approved_hash, o.approved_at, o.approval_snapshot = None, None, None
        o.queued_at, o.queue_key, o.queue_note = None, None, None
        db.add(Audit(action="message_skipped", subject=oid))


def best_result(db, candidate_id):
    """The newest search result for a person, preferring one that carries an AI judgment."""
    results = db.scalars(select(SearchResult).join(SearchRun, SearchRun.id == SearchResult.run_id)
                         .where(SearchResult.candidate_id == candidate_id)
                         .order_by(SearchRun.created.desc())).all()
    return next((r for r in results if r.ai_fit), results[0] if results else None)


def review_items(db) -> list:
    """Drafts waiting for a human decision, best fit first: (outreach, person, search result or None)."""
    rows = db.execute(select(Outreach, Candidate).join(Candidate, Candidate.x_id == Outreach.recipient_id).where(
        Outreach.send_status == "not_sent", Outreach.draft != "", Outreach.queued_at.is_(None),
        Outreach.skipped.is_(False))).all()
    items = [(o, person, best_result(db, person.x_id)) for o, person in rows]
    items.sort(key=lambda i: (fit_rank(i[2].ai_fit if i[2] else None), -(i[2].score if i[2] else 0), i[1].handle))
    return items


def queued_items(db) -> list:
    """Queued messages in sending order: (outreach, person)."""
    return db.execute(select(Outreach, Candidate).join(Candidate, Candidate.x_id == Outreach.recipient_id)
                      .where(Outreach.queued_at.is_not(None)).order_by(Outreach.queued_at, Outreach.id)).all()


def hold_reason(db, settings) -> str | None:
    """Why the queue is not sending right now, checked without spending anything."""
    w = db.get(Workspace, "main")
    if w.paused:
        return "SENDING_PAUSED"
    if not settings.send_enabled:
        return "SENDING_DISABLED"
    accounts = db.scalars(select(Account).where(Account.connected.is_(True))).all()
    if len(accounts) != 1:
        return "ACCOUNT_RECONNECT_REQUIRED"
    if not (settings.history_limit_acknowledged or w.history_acknowledged):
        return "HISTORY_ACKNOWLEDGEMENT_REQUIRED"
    account = accounts[0]
    if account.active_attempt:
        return "SENDER_BUSY"
    if account.cooldown_until and account.cooldown_until > now():
        return "RATE_LIMITED"
    newest = db.scalar(select(func.max(Attempt.started)))
    if newest and (now() - newest).total_seconds() < settings.send_min_gap_seconds:
        return "PACING"
    midnight = now().replace(hour=0, minute=0, second=0, microsecond=0)
    used = db.scalar(select(func.count()).select_from(Attempt).where(Attempt.started >= midnight))
    if used >= settings.daily_send_limit:
        return "DAILY_LIMIT"
    return None


def _settle(db, oid=None):
    """Clear queue entries whose request key already has a final result (for example after a restart)."""
    query = select(Outreach.id, Attempt.status, Attempt.error).join(
        Attempt, Attempt.request_key == Outreach.queue_key).where(Attempt.status != "in_flight")
    if oid:
        query = query.where(Outreach.id == oid)
    found = db.execute(query.order_by(Outreach.queued_at).limit(1)).first()
    if not found:
        return None
    _, _, o = locked_rows(db, found.id)
    if found.status == "rejected" and found.error == "RATE_LIMITED":
        # X refused for rate reasons, so nothing was delivered. Keep the message, its approval and its
        # place; a fresh key lets it be tried once the cooldown set by send() has passed.
        o.queue_key, o.queue_note = secrets.token_urlsafe(24), "RATE_LIMITED"
        return "held:RATE_LIMITED"
    o.queued_at, o.queue_key = None, None
    o.queue_note = found.error if found.status == "rejected" else None
    return found.status


def tick(rt) -> str:
    """One worker step: send at most one queued message if nothing holds the queue."""
    with rt.factory.begin() as db:
        settled = _settle(db)
        if settled:
            return settled
        head = db.scalar(select(Outreach).where(Outreach.queued_at.is_not(None))
                         .order_by(Outreach.queued_at, Outreach.id).limit(1))
        if head is None:
            return "idle"
        held = hold_reason(db, rt.settings)
        if held:
            return "held:" + held
        oid, version, key = head.id, head.version, head.queue_key
    with rt.factory.begin() as db:
        w, a, o = locked_rows(db, oid)
        if o.queue_key != key:
            return "idle"
        blocking = [r for r in eligibility(db, rt.settings, w, a, o, require_approval=False)
                    if r not in HOLD_CODES]
        if blocking:
            o.queued_at, o.queue_key, o.queue_note = None, None, blocking[0]
            db.add(Audit(action="queue_blocked", subject=oid, details={"code": blocking[0]}))
            return "blocked:" + blocking[0]
    try:
        outcome = send(rt, oid, version, key)
    except DomainError as exc:
        code = exc.code
    except ProviderError:
        code = "X_UNAVAILABLE"
    else:
        if outcome not in {"sent", "rejected", "unknown"}:
            return "held:SENDER_BUSY"
        with rt.factory.begin() as db:
            settled = _settle(db, oid)
        return settled if settled and settled.startswith("held:") else outcome
    with rt.factory.begin() as db:
        _, _, o = locked_rows(db, oid)
        if o.queue_key != key:
            return "idle"
        o.queue_note = code
        if code in HOLD_CODES:
            if code in ROTATE_CODES:
                o.queued_at = now()
            return "held:" + code
        o.queued_at, o.queue_key = None, None
        db.add(Audit(action="queue_blocked", subject=oid, details={"code": code}))
        return "blocked:" + code


def _sync_one(rt, oid) -> bool:
    try:
        sync(rt, oid)
        return True
    except (DomainError, ProviderError):
        # Remember the attempt so a failing conversation is not re-read on every worker step.
        with rt.factory.begin() as db:
            db.get(Outreach, oid).last_sync = now()
        return False


def sync_due(rt) -> int:
    """Check replies for sent messages whose last check is older than AUTO_SYNC_MINUTES."""
    minutes = rt.settings.auto_sync_minutes
    if minutes <= 0:
        return 0
    with rt.factory() as db:
        due = list(db.scalars(select(Outreach.id).where(
            Outreach.send_status == "sent", Outreach.sent_at >= now() - timedelta(days=SYNC_WINDOW_DAYS),
            or_(Outreach.last_sync.is_(None), Outreach.last_sync < now() - timedelta(minutes=minutes)),
        ).order_by(Outreach.sent_at)))
    tried = 0
    for oid in due:
        tried += 1
        if not _sync_one(rt, oid):
            # X is failing or the budget is spent: stop this pass rather than repeat the failure.
            break
    return tried


def sync_all(rt) -> tuple[int, int]:
    """Check replies for every sent message now. Returns (succeeded, failed)."""
    with rt.factory() as db:
        sent = list(db.scalars(select(Outreach.id).where(Outreach.send_status == "sent")
                               .order_by(Outreach.sent_at)))
    succeeded = sum(1 for oid in sent if _sync_one(rt, oid))
    return succeeded, len(sent) - succeeded


def backs_off(result: str) -> bool:
    """Whether the worker should pause for BACKOFF_SECONDS after this step."""
    return result.startswith("error:") or result.split(":")[-1] in BACKOFF_CODES


class Worker:
    """Background thread that works the queue. Logs error codes only, never message or error text."""
    def __init__(self, rt):
        self.rt = rt
        self._stop = threading.Event()
        self._thread = None
        self._wait_until = 0.0

    @property
    def alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self):
        self._thread = threading.Thread(target=self._loop, name="outreach-worker", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)

    def run_once(self) -> str:
        try:
            recover_stale(self.rt)
            result = tick(self.rt)
        except Exception as exc:
            code = getattr(exc, "code", None) or type(exc).__name__
            log.warning("worker step failed: %s", code)
            return "error:" + code
        try:
            sync_due(self.rt)
        except Exception as exc:
            log.warning("reply check failed: %s", getattr(exc, "code", None) or type(exc).__name__)
        return result

    def _loop(self):
        while not self._stop.wait(self.rt.settings.queue_tick_seconds):
            if time.monotonic() < self._wait_until:
                continue
            result = self.run_once()
            if backs_off(result):
                self._wait_until = time.monotonic() + BACKOFF_SECONDS
