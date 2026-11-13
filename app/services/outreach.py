from datetime import timedelta

from sqlalchemy import select

from app.db import workspace_lock
from app.errors import DomainError
from app.models import Account, Audit, Candidate, Consent, Evidence, Outreach, Suppression, now
from app.security import digest


def locked_rows(db, outreach_id):
    w = workspace_lock(db)
    peek = db.get(Outreach, outreach_id)
    if peek is None:
        raise DomainError("NOT_FOUND", "This outreach record does not exist.", 404)
    a = db.execute(select(Account).where(Account.x_id == peek.sender_id).with_for_update()).scalar_one()
    o = db.execute(select(Outreach).where(Outreach.id == outreach_id).with_for_update()).scalar_one()
    return w, a, o


def create_outreach(rt, recipient):
    account = rt.active_account()
    with rt.factory.begin() as db:
        workspace_lock(db)
        if not db.get(Candidate, recipient):
            raise DomainError("NOT_FOUND", "Find or register this person first.", 404)
        row = db.scalar(select(Outreach).where(Outreach.sender_id == account.x_id,
                                              Outreach.recipient_id == recipient))
        if row is None:
            row = Outreach(sender_id=account.x_id, recipient_id=recipient)
            db.add(row)
            db.flush()
        return row.id


def registration(rt, handle, reference, controlled):
    account = rt.active_account()
    if not reference.strip() or len(reference) > 500:
        raise DomainError("CONSENT_REQUIRED", "Record a test-consent reference, without secrets.", 400)
    if not controlled and not reference.startswith("https://x.com/"):
        raise DomainError("CONSENT_REQUIRED", "For a recipient you do not control, provide an explicit on-X consent reference.", 400)
    profile = rt.read("user", handle.lstrip("@"))
    recipient = str(profile["id"])
    allowed = rt.settings.allowed_ids if rt.settings.app_mode == "live" else {"fixture_test"}
    if recipient not in allowed or recipient == account.x_id:
        raise DomainError("RECIPIENT_NOT_ALLOWED", "This account is not in the deployment's test allowlist.")
    with rt.factory.begin() as db:
        w = workspace_lock(db)
        person = upsert_registered(db, profile)
        consent = db.scalar(select(Consent).where(Consent.sender_id == account.x_id,
                                                   Consent.recipient_id == person.x_id))
        if consent is None:
            consent = Consent(sender_id=account.x_id, recipient_id=person.x_id)
            db.add(consent)
        else:
            consent.version += 1
        consent.reference, consent.controlled = reference.strip(), controlled
        consent.purpose_version = w.purpose_version
        consent.expires, consent.revoked = now() + timedelta(days=7), False
        for row in db.scalars(select(Outreach).where(Outreach.recipient_id == recipient)):
            row.approved_hash, row.approval_snapshot = None, None
        db.add(Audit(action="test_consent_registered", subject=recipient))
    return recipient


def upsert_registered(db, profile):
    from app.services.discovery import upsert_candidate
    return upsert_candidate(db, profile, manual=True)


def snapshot(db, w, o):
    sources = {}
    if not o.test_message:
        if not o.selected_sources:
            raise DomainError("EVIDENCE_REQUIRED", "Choose evidence or write a clearly labeled test message.")
        for eid in o.selected_sources:
            e = db.get(Evidence, eid)
            if e is None or not e.available or e.candidate_id != o.recipient_id:
                raise DomainError("EVIDENCE_UNAVAILABLE", "The selected public evidence is unavailable.")
            sources[eid] = e.content_hash
    consent = db.scalar(select(Consent).where(Consent.sender_id == o.sender_id,
                                               Consent.recipient_id == o.recipient_id))
    return {"sender": o.sender_id, "recipient": o.recipient_id, "version": o.version,
            "purpose_version": w.purpose_version, "sources": sources,
            "consent_version": consent.version if consent else None,
            "test_message": o.test_message}


def editable(o):
    if o.send_status not in {"not_sent", "rejected"}:
        raise DomainError("ALREADY_CONTACTED", "This message is already sent, in progress, or unresolved.")


def save_draft(rt, oid, expected, text, test_message=False, source_ids=None, metadata=None):
    if not text.strip() or len(text) > 800:
        raise DomainError("INVALID_DRAFT", "Write a message between 1 and 800 characters.", 400)
    with rt.factory.begin() as db:
        w, a, o = locked_rows(db, oid)
        editable(o)
        if o.version != expected:
            raise DomainError("APPROVAL_STALE", "This draft changed in another tab. Refresh and review it.")
        if test_message and db.scalar(select(Consent).where(Consent.sender_id == o.sender_id,
                                                            Consent.recipient_id == o.recipient_id)) is None:
            raise DomainError("CONSENT_REQUIRED", "Register test consent before composing a test message.")
        o.draft, o.test_message = text.strip(), test_message
        o.skipped = False
        o.version += 1
        o.approved_hash, o.approved_at, o.approval_snapshot = None, None, None
        if source_ids is not None:
            o.selected_sources = source_ids[:3]
        o.draft_meta = metadata or {"provider": "manual"}
        snapshot(db, w, o)
        db.add(Audit(action="draft_saved", subject=oid, details={"version": o.version}))
        return o.version


def approve(rt, oid, expected):
    with rt.factory() as db:
        o = db.get(Outreach, oid)
        if o is None:
            raise DomainError("NOT_FOUND", "Message not found.", 404)
        sources = o.selected_sources if not o.test_message else []
    if sources:
        from app.services.discovery import revalidate
        revalidate(rt, sources)
    with rt.factory.begin() as db:
        w, a, o = locked_rows(db, oid)
        editable(o)
        if o.version != expected or not o.draft:
            raise DomainError("APPROVAL_STALE", "Refresh and approve the current message version.")
        o.approval_snapshot = snapshot(db, w, o)
        o.approved_hash, o.approved_at = digest(o.draft), now()
        db.add(Audit(action="message_approved", subject=oid, details={"version": o.version}))


def eligibility(db, settings, w, a, o, require_approval=True):
    reasons = []
    if w.paused:
        reasons.append("SENDING_PAUSED")
    if not a.connected:
        reasons.append("ACCOUNT_RECONNECT_REQUIRED")
    if not settings.send_enabled:
        reasons.append("SENDING_DISABLED")
    if not (settings.history_limit_acknowledged or w.history_acknowledged):
        reasons.append("HISTORY_ACKNOWLEDGEMENT_REQUIRED")
    if a.cooldown_until and a.cooldown_until > now():
        reasons.append("RATE_LIMITED")
    if o.send_status not in {"not_sent", "rejected"}:
        reasons.append("SEND_UNKNOWN" if o.send_status == "unknown" else "ALREADY_CONTACTED")
    # Test messages always need the allowlist and recorded consent. Evidence-based messages
    # to discovered people skip both only when the deployment chose operator_approved.
    gated = o.test_message or settings.outreach_policy != "operator_approved"
    allowed = settings.allowed_ids if settings.app_mode == "live" else {"fixture_test"}
    if (gated and o.recipient_id not in allowed) or o.recipient_id == o.sender_id:
        reasons.append("RECIPIENT_NOT_ALLOWED")
    if db.get(Suppression, o.recipient_id):
        reasons.append("DO_NOT_CONTACT")
    consent = db.scalar(select(Consent).where(Consent.sender_id == o.sender_id,
                                               Consent.recipient_id == o.recipient_id))
    if gated and (not consent or consent.revoked or consent.expires <= now()
                  or consent.purpose_version != w.purpose_version):
        reasons.append("CONSENT_REQUIRED")
    candidate = db.get(Candidate, o.recipient_id)
    if candidate is None or not candidate.available:
        reasons.append("RECIPIENT_UNAVAILABLE")
    if require_approval:
        try:
            current = snapshot(db, w, o)
            if not o.approved_hash or o.approved_hash != digest(o.draft) or o.approval_snapshot != current:
                reasons.append("APPROVAL_STALE")
        except DomainError as e:
            reasons.append(e.code)
        if not o.test_message:
            for eid in o.selected_sources:
                e = db.get(Evidence, eid)
                if e and (now() - e.retrieved).total_seconds() > settings.evidence_max_age_seconds:
                    reasons.append("EVIDENCE_STALE")
                    break
    return reasons


def suppress(rt, recipient, reason="Operator do-not-contact"):
    with rt.factory.begin() as db:
        workspace_lock(db)
        if not db.get(Candidate, recipient):
            raise DomainError("NOT_FOUND", "Candidate not found.", 404)
        if not db.get(Suppression, recipient):
            db.add(Suppression(recipient_id=recipient, reason=reason))
        for o in db.scalars(select(Outreach).where(Outreach.recipient_id == recipient)):
            o.approved_hash = None
            o.approval_snapshot = None
        db.add(Audit(action="recipient_suppressed", subject=recipient))
