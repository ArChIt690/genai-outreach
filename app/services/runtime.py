from contextlib import contextmanager
from datetime import timedelta
from uuid import uuid4

import httpx
from sqlalchemy import select

from app.db import workspace_lock
from app.errors import DomainError
from app.integrations.fixture import FixtureClient
from app.integrations.x_client import XClient
from app.models import Account, now
from app.security import cipher
from app.services.usage import reserve, settle


class Runtime:
    def __init__(self, factory, settings):
        self.factory, self.settings = factory, settings
        self.provider_override = None

    def active_account(self):
        with self.factory() as db:
            rows = db.scalars(select(Account).where(Account.connected.is_(True))).all()
            if len(rows) != 1:
                raise DomainError("ACCOUNT_RECONNECT_REQUIRED", "Connect one authorized sender in Settings.")
            return rows[0]

    def token(self, account_id):
        # Reserve refresh in a short transaction; never hold it across HTTP.
        claim = str(uuid4())
        with self.factory.begin() as db:
            workspace_lock(db)
            a = db.execute(select(Account).where(Account.x_id == account_id).with_for_update()).scalar_one()
            if not a.connected or not a.token:
                raise DomainError("ACCOUNT_RECONNECT_REQUIRED", "Reconnect your sender account.")
            enc = cipher(self.settings)
            if not a.expires or a.expires > now() + timedelta(seconds=60):
                return enc.decrypt(a.token.encode()).decode()
            if a.refresh_claim:
                if a.refresh_claimed_at and now() - a.refresh_claimed_at < timedelta(seconds=60):
                    raise DomainError("TOKEN_REFRESH_BUSY", "Authorization refresh is in progress. Try again shortly.")
                raise DomainError("ACCOUNT_RECONNECT_REQUIRED", "An interrupted refresh requires reconnection.")
            if not a.refresh:
                raise DomainError("ACCOUNT_RECONNECT_REQUIRED", "This authorization expired. Reconnect.")
            refresh = enc.decrypt(a.refresh.encode()).decode()
            a.refresh_claim, a.refresh_claimed_at = claim, now()
        try:
            auth = (self.settings.x_client_id, self.settings.x_client_secret) \
                if self.settings.x_client_secret else None
            response = httpx.post("https://api.x.com/2/oauth2/token", data={
                "grant_type": "refresh_token", "client_id": self.settings.x_client_id,
                "refresh_token": refresh,
            }, auth=auth, timeout=15, follow_redirects=False)
            payload = response.json()
            if response.status_code != 200 or not payload.get("access_token"):
                raise ValueError("rejected")
        except (httpx.HTTPError, ValueError):
            # A rotated token might have been lost. Require reconnect instead of replay.
            raise DomainError("ACCOUNT_RECONNECT_REQUIRED", "Token refresh failed. Reconnect.") from None
        with self.factory.begin() as db:
            workspace_lock(db)
            a = db.execute(select(Account).where(Account.x_id == account_id).with_for_update()).scalar_one()
            if not a.connected or a.refresh_claim != claim:
                raise DomainError("ACCOUNT_RECONNECT_REQUIRED", "Authorization changed during refresh.")
            a.token = enc.encrypt(payload["access_token"].encode()).decode()
            if payload.get("refresh_token"):
                a.refresh = enc.encrypt(payload["refresh_token"].encode()).decode()
            a.expires = now() + timedelta(seconds=int(payload.get("expires_in", 7200)))
            a.refresh_claim, a.refresh_claimed_at = None, None
            return payload["access_token"]

    @contextmanager
    def provider(self, account_id=None):
        if self.provider_override is not None:
            yield self.provider_override
            return
        if self.settings.app_mode == "fixture":
            client = FixtureClient(self.factory)
        else:
            if not account_id:
                account_id = self.active_account().x_id
            client = XClient(self.token(account_id))
        try:
            yield client
        finally:
            client.close()

    def read(self, method, *args, account_id=None, **kwargs):
        bounds = {"me": 10_000, "user": 10_000, "search": 750_000,
                  "posts": max(1, len(args[0]) if args else 1) * 5_000, "events": 200_000}
        usage_id = reserve(self.factory, self.settings, "x_" + method, bounds[method])
        # Any failure conservatively retains its reservation.
        with self.provider(account_id) as provider:
            payload = getattr(provider, method)(*args, **kwargs)
        if method in {"me", "user"}:
            actual = 10_000
        elif method == "search":
            actual = len(payload.get("data") or []) * 5_000 + \
                len(payload.get("includes", {}).get("users") or []) * 10_000
        elif method == "posts":
            actual = len(payload.get("data") or []) * 5_000
        else:
            actual = len(payload.get("data") or []) * 10_000
        settle(self.factory, usage_id, actual)
        return payload
