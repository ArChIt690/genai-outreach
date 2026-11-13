import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import func, select

from app.errors import DomainError, ProviderError
from app.integrations.fixture import FixtureClient
from app.models import Account, DMEvent, Evidence, FixtureMessage, Outreach, Workspace, now
from app.security import cipher
from app.services.discovery import discover
from app.services.drafting import generate
from app.services.outreach import create_outreach
from app.services.sending import send
from app.services.synchronization import reconcile, sync


def test_partial_sync_keeps_pages_but_does_not_claim_complete(rt, prepared):
    send(rt, prepared, 1, secrets.token_urlsafe(24))

    class Partial(FixtureClient):
        def events(self, recipient, cursor=None):
            if cursor:
                raise ProviderError("X_NETWORK_UNCERTAIN")
            page = super().events(recipient)
            page["meta"] = {"next_token": "next-page"}
            return page
    rt.provider_override = Partial(rt.factory)
    with pytest.raises(DomainError) as error:
        sync(rt, prepared)
    assert error.value.code == "SYNC_INCOMPLETE"
    with rt.factory() as db:
        assert db.scalar(select(func.count()).select_from(DMEvent)) == 1
        assert not db.get(Outreach, prepared).sync_complete
        assert db.get(Outreach, prepared).last_sync is None
    rt.provider_override = None
    sync(rt, prepared)
    with rt.factory() as db:
        assert db.get(Outreach, prepared).sync_complete
        assert db.scalar(select(func.count()).select_from(DMEvent)) == 1


def test_repeated_history_cursor_cannot_authorize_send(rt, prepared):
    class Repeated(FixtureClient):
        def events(self, recipient, cursor=None):
            return {"data": [], "meta": {"next_token": "same"}}
    rt.provider_override = Repeated(rt.factory)
    with pytest.raises(DomainError) as error:
        send(rt, prepared, 1, secrets.token_urlsafe(24))
    assert error.value.code == "HISTORY_INCOMPLETE"


def test_prior_contact_prevents_new_initial_message(rt, prepared):
    with rt.factory.begin() as db:
        db.add(FixtureMessage(recipient_id="fixture_test", sender_id="fixture_sender",
                              text="Earlier unrelated contact", created=now() - timedelta(days=1)))
    with pytest.raises(DomainError) as error:
        send(rt, prepared, 1, secrets.token_urlsafe(24))
    assert error.value.code == "ALREADY_CONTACTED"
    with rt.factory() as db:
        assert db.get(Outreach, prepared).send_status == "preexisting_contact"


def test_ambiguous_reconciliation_remains_unknown(rt, prepared):
    class Ambiguous(FixtureClient):
        def send(self, recipient, text):
            super().send(recipient, text)
            super().send(recipient, text)
            raise ProviderError("X_NETWORK_UNCERTAIN")
    rt.provider_override = Ambiguous(rt.factory)
    assert send(rt, prepared, 1, secrets.token_urlsafe(24)) == "unknown"
    with pytest.raises(DomainError):
        reconcile(rt, prepared)
    with rt.factory() as db:
        assert db.get(Outreach, prepared).send_status == "unknown"


def test_purpose_change_during_history_is_rechecked_before_dispatch(rt, prepared):
    class Changed(FixtureClient):
        calls = 0

        def events(self, recipient, cursor=None):
            with self.factory.begin() as db:
                db.get(Workspace, "main").purpose_version += 1
            return {"data": [], "meta": {}}

        def send(self, recipient, text):
            self.calls += 1
    provider = Changed(rt.factory)
    rt.provider_override = provider
    with pytest.raises(DomainError):
        send(rt, prepared, 1, secrets.token_urlsafe(24))
    assert provider.calls == 0


def test_model_unavailable_falls_back_without_network_in_fixture_mode(rt, monkeypatch):
    discover(rt, "robotics")
    oid = create_outreach(rt, "fixture_ada")
    rt.settings.draft_provider = "anthropic"
    rt.settings.anthropic_api_key = "synthetic-test-key"
    rt.settings.anthropic_model = "test-model"
    rt.settings.model_data_use_acknowledged = True

    def forbidden(*args, **kwargs):
        pytest.fail("Fixture mode attempted model network access")
    monkeypatch.setattr(httpx, "post", forbidden)
    generate(rt, oid, 0, "test-session")
    with rt.factory() as db:
        meta = db.get(Outreach, oid).draft_meta
        assert meta["provider"] == "evidence template"
        assert meta["fallback"]


@pytest.mark.parametrize("response_kind", ["timeout", "fabricated_source"])
def test_model_failure_falls_back_and_never_receives_private_dms(rt, monkeypatch, response_kind):
    discover(rt, "robotics")
    oid = create_outreach(rt, "fixture_ada")
    rt.settings.app_mode = "live"
    rt.settings.draft_provider = "anthropic"
    rt.settings.anthropic_api_key = "synthetic-test-key"
    rt.settings.anthropic_model = "test-model"
    rt.settings.model_data_use_acknowledged = True
    rt.provider_override = FixtureClient(rt.factory)
    captured = []

    def model_post(*args, **kwargs):
        captured.append(kwargs["json"])
        if response_kind == "timeout":
            raise httpx.ReadTimeout("redacted")
        import json
        return httpx.Response(200, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
                              json={"content": [{"type": "text", "text": json.dumps({
                                  "draft_text": "Invented", "claims": [{"source_id": "fake", "quote": "fake"}],
                                  "uncertainties": [],
                              })}]})
    monkeypatch.setattr(httpx, "post", model_post)
    generate(rt, oid, 0, "test-session")
    with rt.factory() as db:
        assert db.get(Outreach, oid).draft_meta["provider"] == "evidence template"
    assert len(captured) == 1
    assert "dm_events" not in str(captured[0])
    assert "synthetic-test-key" not in str(captured[0])


@pytest.mark.postgres
def test_refresh_rotation_is_coordinated_without_double_refresh(rt, monkeypatch):
    encryption = cipher(rt.settings)
    with rt.factory.begin() as db:
        account = db.get(Account, "fixture_sender")
        account.token = encryption.encrypt(b"old-access").decode()
        account.refresh = encryption.encrypt(b"old-refresh").decode()
        account.expires = now() - timedelta(minutes=1)
    entered = threading.Event()
    calls = []

    def post(*args, **kwargs):
        calls.append(True)
        entered.set()
        time.sleep(.15)
        return httpx.Response(200, json={"access_token": "new-access", "refresh_token": "new-refresh",
                                        "expires_in": 7200})
    monkeypatch.setattr(httpx, "post", post)
    with ThreadPoolExecutor(2) as executor:
        first = executor.submit(rt.token, "fixture_sender")
        assert entered.wait(timeout=2)
        with pytest.raises(DomainError) as error:
            rt.token("fixture_sender")
        assert error.value.code == "TOKEN_REFRESH_BUSY"
        assert first.result() == "new-access"
    assert len(calls) == 1
    with rt.factory() as db:
        assert encryption.decrypt(db.get(Account, "fixture_sender").refresh.encode()) == b"new-refresh"


def test_private_text_is_not_copied_into_discovery_sources(rt):
    discover(rt, "robotics")
    with rt.factory() as db:
        assert all(e.candidate_id.startswith("fixture_") for e in db.scalars(select(Evidence)))
