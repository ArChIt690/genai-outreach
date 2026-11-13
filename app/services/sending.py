
from sqlalchemy import func, select

from app.errors import DomainError, ProviderError
from app.integrations.x_client import parse_time
from app.models import Attempt, Audit, Outreach, Usage, now
from app.security import digest
from app.services.outreach import eligibility, locked_rows
from app.services.synchronization import history_check


def send(rt, oid, expected, request_key):
    if not 16 <= len(request_key) <= 80:
        raise DomainError("INVALID_REQUEST_KEY", "A valid request key is required.", 400)
    with rt.factory() as db:
        prior = db.scalar(select(Attempt).where(Attempt.request_key == request_key))
        if prior:
            if prior.outreach_id != oid:
                raise DomainError("REQUEST_KEY_CONFLICT", "This request key belongs to another message.")
            return prior.status
        o = db.get(Outreach, oid)
        if not o:
            raise DomainError("NOT_FOUND", "Message not found.", 404)
        sender, recipient = o.sender_id, o.recipient_id
        sources = list(o.selected_sources) if not o.test_message else []
    if sources:
        from app.services.discovery import revalidate
        revalidate(rt, sources)
    # A first pass rejects obvious blocks before spending credits on history.
    with rt.factory.begin() as db:
        w, a, o = locked_rows(db, oid)
        reasons = eligibility(db, rt.settings, w, a, o)
        if reasons:
            raise DomainError(reasons[0], "Sending is blocked: " + ", ".join(reasons))
    events = history_check(rt, recipient, sender)
    outgoing = [e for e in events if str(e.get("sender_id")) == sender]
    if outgoing:
        with rt.factory.begin() as db:
            _, _, o = locked_rows(db, oid)
            if o.send_status in {"not_sent", "rejected"}:
                o.send_status = "preexisting_contact"
        raise DomainError("ALREADY_CONTACTED", "An outgoing message already exists in available history.")
    # Resolve/refresh token BEFORE committing a potentially dispatched attempt.
    with rt.provider(sender) as provider:
        with rt.factory.begin() as db:
            w, a, o = locked_rows(db, oid)
            prior = db.scalar(select(Attempt).where(Attempt.request_key == request_key))
            if prior:
                if prior.outreach_id != oid:
                    raise DomainError("REQUEST_KEY_CONFLICT", "Request key belongs to another message.")
                return prior.status
            reasons = eligibility(db, rt.settings, w, a, o)
            if reasons or o.version != expected:
                raise DomainError(reasons[0] if reasons else "APPROVAL_STALE",
                                  "The message or eligibility changed. Refresh and review it.")
            if a.active_attempt:
                raise DomainError("SENDER_BUSY", "Resolve the sender's pending message before sending another.")
            midnight = now().replace(hour=0, minute=0, second=0, microsecond=0)
            used = db.scalar(select(func.count()).select_from(Attempt).where(Attempt.started >= midnight))
            if used >= rt.settings.daily_send_limit:
                raise DomainError("DAILY_LIMIT", "Today's configured test dispatch allowance is exhausted.")
            if w.spend_micros + 15_000 > round(rt.settings.x_budget_usd * 1_000_000):
                raise DomainError("BUDGET_EXCEEDED", "The configured X usage allowance is exhausted.")
            w.spend_micros += 15_000
            db.add(Usage(kind="x_send", reserved_micros=15_000, settled_micros=15_000))
            attempt = Attempt(outreach_id=oid, request_key=request_key, text=o.draft, payload_hash=digest(o.draft))
            db.add(attempt)
            db.flush()
            a.active_attempt, o.send_status = attempt.id, "in_flight"
            aid, text = attempt.id, attempt.text
            db.add(Audit(action="send_reserved", subject=oid, details={"attempt": aid, "version": expected}))
        outcome, error, result = "unknown", None, None
        retry_at = None
        try:
            result = provider.send(recipient, text)
            if not isinstance(result, dict) or not result.get("dm_event_id") or not result.get("dm_conversation_id"):
                raise ProviderError("X_MALFORMED_SUCCESS")
            outcome = "sent"
        except ProviderError as exc:
            outcome = "rejected" if exc.definitive else "unknown"
            error, retry_at = exc.code, exc.retry_at
        except Exception:
            # After the reservation, even an unexpected failure is potentially delivered.
            error = "UNEXPECTED_DISPATCH_FAILURE"
        with rt.factory.begin() as db:
            _, a, o = locked_rows(db, oid)
            attempt = db.get(Attempt, aid)
            attempt.status, attempt.error, attempt.finished = outcome, error, now()
            o.send_status = outcome
            if outcome == "sent":
                attempt.external_id = str(result["dm_event_id"])
                o.conversation_id = str(result["dm_conversation_id"])
                o.sent_at = parse_time(result["created_at"]) if result.get("created_at") else now()
            if retry_at:
                a.cooldown_until = retry_at
            if outcome in {"sent", "rejected"} and a.active_attempt == aid:
                a.active_attempt = None
            if outcome == "rejected":
                o.approved_hash, o.approval_snapshot = None, None
            db.add(Audit(action="send_" + outcome, subject=oid, details={"attempt": aid, "code": error}))
        return outcome
