from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.db import workspace_lock
from app.errors import DomainError, ProviderError
from app.integrations.x_client import parse_time
from app.models import Account, Attempt, Audit, DMEvent, Outreach, Suppression, now
from app.services.outreach import locked_rows


def conversation_pages(rt, recipient, account_id):
    cursor = None
    seen = set()
    for _ in range(10):
        page = rt.read("events", recipient, cursor=cursor, account_id=account_id)
        if page.get("errors") or not isinstance(page.get("data"), list):
            if page.get("errors") or page.get("meta", {}).get("result_count") != 0:
                raise DomainError("HISTORY_INCOMPLETE", "X did not return complete conversation history.")
        for event in page.get("data") or []:
            if not all(k in event for k in ("id", "sender_id", "created_at")):
                raise DomainError("HISTORY_INCOMPLETE", "A conversation event is missing required fields.")
            try:
                parse_time(event["created_at"])
            except (ValueError, TypeError, AttributeError):
                raise DomainError("HISTORY_INCOMPLETE", "A conversation event has an invalid timestamp.") from None
        yield page
        cursor = page.get("meta", {}).get("next_token")
        if not cursor:
            return
        if cursor in seen:
            raise DomainError("HISTORY_INCOMPLETE", "X returned a repeated history cursor.")
        seen.add(cursor)
    raise DomainError("HISTORY_INCOMPLETE", "History exceeded the 200-event safety cap.")


def history_check(rt, recipient, account_id):
    events = []
    try:
        for page in conversation_pages(rt, recipient, account_id):
            events.extend(page.get("data") or [])
    except ProviderError:
        raise DomainError("HISTORY_INCOMPLETE", "Conversation history could not be verified.") from None
    return events


def sync(rt, oid):
    with rt.factory() as db:
        o = db.get(Outreach, oid)
        if o is None:
            raise DomainError("NOT_FOUND", "Message not found.", 404)
        sender, recipient = o.sender_id, o.recipient_id
    try:
        for page in conversation_pages(rt, recipient, sender):
            with rt.factory.begin() as db:
                workspace_lock(db)
                for event in page.get("data") or []:
                    if not all(k in event for k in ("id", "sender_id", "created_at")):
                        raise DomainError("SYNC_INCOMPLETE", "A conversation event was incomplete.")
                    event_sender = str(event["sender_id"])
                    if event_sender not in {sender, recipient}:
                        continue
                    db.execute(insert(DMEvent).values(
                        account_id=sender, recipient_id=recipient, external_id=str(event["id"]),
                        conversation_id=event.get("dm_conversation_id") or "",
                        sender_id=event_sender, text=event.get("text", ""),
                        created=parse_time(event["created_at"]),
                    ).on_conflict_do_nothing(index_elements=["account_id", "external_id"]))
                    text = event.get("text", "").strip().lower().rstrip(".!")
                    if event_sender == recipient and (text == "stop" or "do not contact me" in text):
                        if db.get(Suppression, recipient) is None:
                            db.add(Suppression(recipient_id=recipient, reason="Explicit recipient opt-out"))
                        for related in db.scalars(select(Outreach).where(Outreach.recipient_id == recipient)):
                            related.approved_hash, related.approval_snapshot = None, None
        with rt.factory.begin() as db:
            workspace_lock(db)
            row = db.get(Outreach, oid)
            row.last_sync, row.sync_complete, row.sync_error = now(), True, None
    except (DomainError, ProviderError) as exc:
        with rt.factory.begin() as db:
            workspace_lock(db)
            row = db.get(Outreach, oid)
            row.sync_complete, row.sync_error = False, exc.code
        raise DomainError("SYNC_INCOMPLETE", "Sync is incomplete. Stored pages are safe; try syncing again.") from None


def reply_state(db, o):
    if not o.sent_at:
        return "No confirmed initial send"
    events = db.scalars(select(DMEvent).where(
        DMEvent.account_id == o.sender_id, DMEvent.recipient_id == o.recipient_id,
        DMEvent.sender_id == o.recipient_id, DMEvent.created > o.sent_at,
    ).order_by(DMEvent.created)).all()
    if any(o.acknowledged_at is None or e.created > o.acknowledged_at for e in events):
        return "Needs attention"
    return "Handled" if events else "Awaiting reply"


def acknowledge(rt, oid):
    with rt.factory.begin() as db:
        _, _, o = locked_rows(db, oid)
        latest = db.scalar(select(DMEvent.created).where(
            DMEvent.account_id == o.sender_id, DMEvent.recipient_id == o.recipient_id,
            DMEvent.sender_id == o.recipient_id).order_by(DMEvent.created.desc()).limit(1))
        if latest:
            o.acknowledged_at = latest
        db.add(Audit(action="replies_acknowledged", subject=oid))


def recover_stale(rt):
    with rt.factory.begin() as db:
        workspace_lock(db)
        for account in db.scalars(select(Account).with_for_update()):
            if not account.active_attempt:
                continue
            attempt = db.get(Attempt, account.active_attempt)
            if attempt and attempt.status == "in_flight" and \
                    now() - attempt.started > timedelta(seconds=rt.settings.stale_send_seconds):
                attempt.status, attempt.error, attempt.finished = "unknown", "PROCESS_INTERRUPTED", now()
                db.get(Outreach, attempt.outreach_id).send_status = "unknown"


def reconcile(rt, oid):
    with rt.factory() as db:
        o = db.get(Outreach, oid)
        if o is None:
            raise DomainError("NOT_FOUND", "Message not found.", 404)
        attempt = db.scalar(select(Attempt).where(Attempt.outreach_id == oid, Attempt.status == "unknown")
                            .order_by(Attempt.started.desc()))
        if not attempt:
            raise DomainError("NOT_UNKNOWN", "There is no uncertain send to reconcile.")
        sender, recipient, text, started = o.sender_id, o.recipient_id, attempt.text, attempt.started
        aid = attempt.id
    events = history_check(rt, recipient, sender)
    matches = [e for e in events if str(e.get("sender_id")) == sender and
               " ".join(e.get("text", "").split()) == " ".join(text.split()) and
               started - timedelta(seconds=5) <= parse_time(e["created_at"]) <= started + timedelta(seconds=90)
               and e.get("dm_conversation_id")]
    if len(matches) != 1:
        raise DomainError("SEND_UNKNOWN", "No unique matching message was found. Resending remains blocked.")
    event = matches[0]
    with rt.factory.begin() as db:
        _, account, o = locked_rows(db, oid)
        attempt = db.get(Attempt, aid)
        if attempt.status != "unknown":
            return
        attempt.status, attempt.external_id, attempt.finished = "sent", str(event["id"]), now()
        o.send_status, o.sent_at = "sent", parse_time(event["created_at"])
        o.conversation_id = event["dm_conversation_id"]
        if account.active_attempt == aid:
            account.active_attempt = None
        db.add(Audit(action="send_reconciled", subject=oid))
