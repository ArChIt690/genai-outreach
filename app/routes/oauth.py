import base64
import hashlib
import secrets
from datetime import timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from app.db import workspace_lock
from app.errors import DomainError, ProviderError
from app.integrations.x_client import SCOPES, XClient
from app.models import Account, Audit, now
from app.security import cipher, digest, locked_session, session_for

router = APIRouter()


@router.get("/oauth/x/start")
def start(request: Request):
    operator = session_for(request)
    settings, factory = request.app.state.settings, request.app.state.factory
    if settings.app_mode != "live":
        raise DomainError("FIXTURE_MODE", "Fixture mode uses a synthetic connected account.")
    if not settings.x_client_id or not settings.token_encryption_key:
        raise DomainError("SETUP_REQUIRED", "Configure X_CLIENT_ID and token encryption before connecting.", 503)
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
    with factory.begin() as db:
        row = locked_session(db, operator.token_hash)
        row.oauth_state_hash, row.oauth_verifier = digest(state), cipher(settings).encrypt(verifier.encode()).decode()
        row.oauth_expires = now() + timedelta(minutes=10)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return RedirectResponse("https://x.com/i/oauth2/authorize?" + urlencode({
        "response_type": "code", "client_id": settings.x_client_id,
        "redirect_uri": settings.x_callback_url, "scope": SCOPES, "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256",
    }), status_code=303)


@router.get("/oauth/x/callback")
def callback(request: Request):
    operator = session_for(request)
    settings, factory = request.app.state.settings, request.app.state.factory
    if settings.app_mode != "live":
        raise DomainError("FIXTURE_MODE", "OAuth is disabled in fixture mode.")
    state, code = request.query_params.get("state", ""), request.query_params.get("code", "")
    with factory.begin() as db:
        row = locked_session(db, operator.token_hash)
        if not code or not row.oauth_state_hash or not row.oauth_expires or row.oauth_expires <= now() or \
                not secrets.compare_digest(row.oauth_state_hash, digest(state)):
            raise DomainError("OAUTH_STATE_INVALID", "Authorization state expired or did not match.", 403)
        verifier = cipher(settings).decrypt(row.oauth_verifier.encode()).decode()
        row.oauth_state_hash, row.oauth_verifier, row.oauth_expires = None, None, None
    # State is consumed before the external request, preventing replay.
    try:
        auth = (settings.x_client_id, settings.x_client_secret) if settings.x_client_secret else None
        response = httpx.post("https://api.x.com/2/oauth2/token", data={
            "grant_type": "authorization_code", "code": code, "client_id": settings.x_client_id,
            "redirect_uri": settings.x_callback_url, "code_verifier": verifier,
        }, auth=auth, timeout=15, follow_redirects=False)
        payload = response.json()
        if response.status_code != 200 or not payload.get("access_token"):
            raise ValueError("rejected")
        if not set(SCOPES.split()).issubset(set(payload.get("scope", "").split())):
            raise DomainError("OAUTH_SCOPE_MISSING", "X did not grant all required permissions. Reconnect.")
        client = XClient(payload["access_token"])
        try:
            me = client.me()
        finally:
            client.close()
    except (httpx.HTTPError, ValueError, ProviderError):
        raise DomainError("OAUTH_EXCHANGE_FAILED", "X authorization failed. Start connection again.") from None
    with factory.begin() as db:
        workspace_lock(db)
        accounts = db.scalars(select(Account).with_for_update()).all()
        if any(a.active_attempt for a in accounts):
            raise DomainError("SENDER_BUSY", "Resolve the existing sender's outstanding attempt first.")
        for account in accounts:
            account.connected, account.token, account.refresh = False, None, None
        account = db.get(Account, str(me["id"]))
        if account is None:
            account = Account(x_id=str(me["id"]), handle=me["username"])
            db.add(account)
        enc = cipher(settings)
        account.handle, account.connected = me["username"], True
        account.token = enc.encrypt(payload["access_token"].encode()).decode()
        account.refresh = enc.encrypt(payload["refresh_token"].encode()).decode() if payload.get("refresh_token") else None
        account.expires = now() + timedelta(seconds=int(payload.get("expires_in", 7200)))
        account.scopes, account.refresh_claim, account.refresh_claimed_at = payload["scope"], None, None
        db.add(Audit(action="account_connected", subject=account.x_id))
    return RedirectResponse("/settings?notice=Account+connected", status_code=303)
