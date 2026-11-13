import secrets
from datetime import timedelta
from threading import Lock

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app.db import workspace_lock
from app.errors import DomainError
from app.models import Account, Audit, Candidate, Consent, Evidence, FixtureMessage, OperatorSession, Outreach, now
from app.security import csrf_check, new_session, session_for, verify_password
from app.services.discovery import discover, invalidate_source, revalidate
from app.services.drafting import generate
from app.services.outreach import approve, create_outreach, locked_rows, registration, save_draft, suppress
from app.services.sending import send
from app.services.synchronization import acknowledge, reconcile, sync

router = APIRouter()
login_attempts = {}
login_lock = Lock()


def handle(request, form):
    rt = request.app.state.runtime
    path = request.url.path
    if path == "/login":
        ip = request.client.host if request.client else "local"
        with login_lock:
            cutoff = now() - timedelta(minutes=10)
            entries = [t for t in login_attempts.get(ip, []) if t > cutoff]
            if len(entries) >= 5:
                raise DomainError("LOGIN_THROTTLED", "Wait ten minutes before trying again.", 429)
            login_attempts[ip] = entries + [now()]
        cookie = request.cookies.get("login_csrf", "")
        if not cookie or not secrets.compare_digest(cookie, form.get("csrf", "")) or \
                (request.headers.get("origin") and request.headers["origin"] != rt.settings.app_origin):
            raise DomainError("CSRF_REJECTED", "Reload the sign-in page and try again.", 403)
        if not rt.settings.operator_password_hash:
            raise DomainError("SETUP_REQUIRED", "Run the bootstrap script to set an operator password.", 503)
        if not verify_password(rt.settings.operator_password_hash, form.get("password", "")):
            raise DomainError("LOGIN_FAILED", "The operator password was not accepted.", 401)
        with login_lock:
            login_attempts.pop(ip, None)
        token = new_session(rt.factory, rt.settings.session_hours)
        response = RedirectResponse("/discover", status_code=303)
        response.set_cookie("operator", token, httponly=True, secure=rt.settings.secure_cookie,
                            samesite="lax", max_age=rt.settings.session_hours * 3600)
        response.delete_cookie("login_csrf")
        return response
    operator = session_for(request)
    csrf_check(request, operator, form.get("csrf"))
    destination = "/settings"
    if path == "/logout":
        with rt.factory.begin() as db:
            db.delete(db.get(OperatorSession, operator.token_hash))
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie("operator")
        return response
    if path == "/settings/save":
        sender, purpose = form.get("sender_name", "").strip(), form.get("purpose", "").strip()
        if not sender or len(sender) > 100 or not purpose or len(purpose) > 300:
            raise DomainError("INVALID_PURPOSE", "Supply a sender name and a purpose of up to 300 characters.", 400)
        with rt.factory.begin() as db:
            w = workspace_lock(db)
            if w.sender_name != sender or w.purpose != purpose:
                w.sender_name, w.purpose = sender, purpose
                w.purpose_version += 1
                for o in db.scalars(select(Outreach)):
                    o.approved_hash, o.approval_snapshot = None, None
            w.history_acknowledged = form.get("history_acknowledged") == "on"
            db.add(Audit(action="settings_saved", subject="main"))
    elif path == "/settings/pause":
        with rt.factory.begin() as db:
            w = workspace_lock(db)
            w.paused = not w.paused
            db.add(Audit(action="sending_paused" if w.paused else "sending_resumed", subject="main"))
    elif path == "/settings/disconnect":
        with rt.factory.begin() as db:
            w = workspace_lock(db)
            w.paused = True
            for a in db.scalars(select(Account).with_for_update()):
                a.token, a.refresh, a.connected, a.refresh_claim = None, None, False, None
            db.add(Audit(action="account_disconnected", subject="main"))
    elif path == "/settings/purge":
        with rt.factory.begin() as db:
            workspace_lock(db)
            for e in db.scalars(select(Evidence)):
                invalidate_source(db, e.id)
                e.text, e.available, e.content_hash = "", False, ""
            for candidate in db.scalars(select(Candidate)):
                candidate.bio, candidate.location = "", ""
            # Preserve identity and send ledger; private bodies can be purged separately by the same action.
            from app.models import DMEvent
            for event in db.scalars(select(DMEvent)):
                event.text = ""
            for row in db.scalars(select(Outreach)):
                if row.send_status in {"not_sent", "rejected"}:
                    row.draft = ""
            db.add(Audit(action="local_content_purged", subject="main"))
    elif path == "/test-recipients":
        recipient = registration(rt, form.get("handle", ""), form.get("reference", ""),
                                 form.get("controlled") == "on")
        destination = f"/candidates/{recipient}"
    elif path.startswith("/test-recipients/") and path.endswith("/revoke"):
        with rt.factory.begin() as db:
            workspace_lock(db)
            consent = db.get(Consent, request.path_params["id"])
            if not consent:
                raise DomainError("NOT_FOUND", "Consent record not found.", 404)
            consent.revoked, consent.version = True, consent.version + 1
            for o in db.scalars(select(Outreach).where(Outreach.recipient_id == consent.recipient_id)):
                o.approved_hash, o.approval_snapshot = None, None
            db.add(Audit(action="test_consent_revoked", subject=consent.recipient_id))
    elif path == "/searches":
        run = discover(rt, form.get("topics", ""), form.get("roles", ""), form.get("location", ""))
        destination = f"/discover?run={run}"
    elif path == "/outreach":
        create_outreach(rt, form.get("recipient", ""))
        destination = "/candidates/" + form.get("recipient", "")
    elif path.startswith("/outreach/"):
        oid = request.path_params["id"]
        with rt.factory() as db:
            row = db.get(Outreach, oid)
            if not row:
                raise DomainError("NOT_FOUND", "Message not found.", 404)
            destination = f"/candidates/{row.recipient_id}"
        action = path.rsplit("/", 1)[-1]
        expected = int(form.get("version", "-1"))
        if action == "draft":
            generate(rt, oid, expected, operator.token_hash)
        elif action == "edit":
            save_draft(rt, oid, expected, form.get("text", ""), form.get("test_message") == "on")
        elif action == "approve":
            approve(rt, oid, expected)
        elif action == "send":
            outcome = send(rt, oid, expected, form.get("request_key", ""))
            destination += f"?notice=Send+status:+{outcome}"
        elif action == "sync":
            sync(rt, oid)
        elif action == "acknowledge":
            acknowledge(rt, oid)
        elif action == "reconcile":
            reconcile(rt, oid)
        elif action == "freeze":
            suppress(rt, row.recipient_id, "Operator froze this conversation; uncertain send remains unresolved")
        else:
            raise DomainError("NOT_FOUND", "Unknown action.", 404)
    elif path.startswith("/candidates/") and path.endswith("/suppress"):
        recipient = request.path_params["id"]
        suppress(rt, recipient)
        destination = "/candidates/" + recipient
    elif path.startswith("/candidates/") and path.endswith("/refresh"):
        recipient = request.path_params["id"]
        with rt.factory() as db:
            ids = list(db.scalars(select(Evidence.id).where(Evidence.candidate_id == recipient).limit(3)))
        revalidate(rt, ids)
        destination = "/candidates/" + recipient
    elif path.startswith("/fixture/reply/"):
        if rt.settings.app_mode != "fixture":
            raise DomainError("NOT_FOUND", "Unknown action.", 404)
        with rt.factory.begin() as db:
            _, _, row = locked_rows(db, request.path_params["id"])
            if row.send_status != "sent":
                raise DomainError("NOT_SENT", "Send the fixture message before simulating its reply.")
            text = form.get("text", "").strip()
            if not text or len(text) > 800:
                raise DomainError("INVALID_REPLY", "Write a short synthetic reply.", 400)
            db.add(FixtureMessage(recipient_id=row.recipient_id, sender_id=row.recipient_id, text=text))
            destination = f"/candidates/{row.recipient_id}"
    else:
        raise DomainError("NOT_FOUND", "Unknown action.", 404)
    return RedirectResponse(destination, status_code=303)


async def post_action(request: Request):
    try:
        form = dict(await request.form(max_fields=20))
        return await run_in_threadpool(handle, request, form)
    except ValueError:
        raise DomainError("INVALID_INPUT", "A submitted field was invalid. Refresh and try again.", 400) from None


for route in [
    "/login", "/logout", "/settings/save", "/settings/pause", "/settings/disconnect", "/settings/purge",
    "/test-recipients", "/test-recipients/{id}/revoke", "/searches", "/outreach",
    "/outreach/{id}/draft", "/outreach/{id}/edit", "/outreach/{id}/approve", "/outreach/{id}/send",
    "/outreach/{id}/sync", "/outreach/{id}/reconcile", "/outreach/{id}/acknowledge", "/outreach/{id}/freeze",
    "/candidates/{id}/suppress", "/candidates/{id}/refresh", "/fixture/reply/{id}",
]:
    router.add_api_route(route, post_action, methods=["POST"], name=route.replace("/", "_"))
