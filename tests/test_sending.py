import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.errors import DomainError, ProviderError
from app.integrations.fixture import FixtureClient
from app.models import Account, Attempt, Consent, DMEvent, FixtureMessage, Outreach, Workspace, now
from app.services.outreach import approve, create_outreach, save_draft, suppress
from app.services.sending import send
from app.services.synchronization import acknowledge, reconcile, recover_stale, reply_state, sync
from app.services.usage import reserve


def key():
    return secrets.token_urlsafe(24)


def test_send_and_request_replay(rt, prepared):
    request_key = key()
    assert send(rt, prepared, 1, request_key) == "sent"
    assert send(rt, prepared, 1, request_key) == "sent"
    with pytest.raises(DomainError):
        send(rt, prepared, 1, key())
    with rt.factory() as db:
        assert db.scalar(select(func.count()).select_from(FixtureMessage)) == 1


def test_edit_invalidates_approval(rt, prepared):
    save_draft(rt, prepared, 1, "Revised prototype test. Reply STOP to opt out.", True)
    with pytest.raises(DomainError, match="APPROVAL_STALE"):
        send(rt, prepared, 2, key())
    with pytest.raises(DomainError):
        approve(rt, prepared, 1)


@pytest.mark.parametrize("change,code", [
    ("revoked", "CONSENT_REQUIRED"), ("expired", "CONSENT_REQUIRED"),
    ("purpose", "CONSENT_REQUIRED"), ("suppressed", "DO_NOT_CONTACT"),
    ("paused", "SENDING_PAUSED"), ("disconnected", "ACCOUNT_RECONNECT_REQUIRED"),
    ("disabled", "SENDING_DISABLED"), ("unacknowledged", "HISTORY_ACKNOWLEDGEMENT_REQUIRED"),
])
def test_server_side_eligibility(rt, prepared, change, code):
    with rt.factory.begin() as db:
        consent = db.scalar(select(Consent))
        if change == "revoked":
            consent.revoked = True
        elif change == "expired":
            consent.expires = now() - timedelta(seconds=1)
        elif change == "purpose":
            db.get(Workspace, "main").purpose_version += 1
        elif change == "paused":
            db.get(Workspace, "main").paused = True
        elif change == "disconnected":
            db.get(Account, "fixture_sender").connected = False
        elif change == "disabled":
            rt.settings.send_enabled = False
        elif change == "unacknowledged":
            rt.settings.history_limit_acknowledged = False
    if change == "suppressed":
        suppress(rt, "fixture_test")
    with pytest.raises(DomainError) as error:
        send(rt, prepared, 1, key())
    assert error.value.code == code


@pytest.mark.postgres
def test_concurrent_send_has_one_provider_call(rt, prepared):
    class Slow(FixtureClient):
        calls = 0
        guard = threading.Lock()

        def send(self, recipient, text):
            with self.guard:
                self.calls += 1
            time.sleep(0.15)
            return super().send(recipient, text)
    provider = Slow(rt.factory)
    rt.provider_override = provider
    barrier = threading.Barrier(2)

    def run():
        barrier.wait()
        try:
            return send(rt, prepared, 1, key())
        except DomainError as error:
            return error.code
    with ThreadPoolExecutor(2) as executor:
        results = list(executor.map(lambda _: run(), range(2)))
    assert provider.calls == 1, results
    assert "sent" in results


def test_accepted_then_timeout_never_retries_and_reconciles(rt, prepared):
    class LostResponse(FixtureClient):
        calls = 0

        def send(self, recipient, text):
            self.calls += 1
            super().send(recipient, text)
            raise ProviderError("X_NETWORK_UNCERTAIN")
    provider = LostResponse(rt.factory)
    rt.provider_override = provider
    assert send(rt, prepared, 1, key()) == "unknown"
    with pytest.raises(DomainError):
        send(rt, prepared, 1, key())
    assert provider.calls == 1
    reconcile(rt, prepared)
    with rt.factory() as db:
        assert db.get(Outreach, prepared).send_status == "sent"
        assert db.get(Account, "fixture_sender").active_attempt is None


def test_no_evidence_does_not_prove_failed_delivery(rt, prepared):
    class Timeout(FixtureClient):
        def send(self, recipient, text):
            raise ProviderError("X_NETWORK_UNCERTAIN")
    rt.provider_override = Timeout(rt.factory)
    assert send(rt, prepared, 1, key()) == "unknown"
    with pytest.raises(DomainError) as error:
        reconcile(rt, prepared)
    assert error.value.code == "SEND_UNKNOWN"
    with rt.factory() as db:
        assert db.get(Account, "fixture_sender").active_attempt


@pytest.mark.parametrize("code,status,definitive,outcome", [
    ("ACCOUNT_RECONNECT_REQUIRED", 401, True, "rejected"),
    ("RATE_LIMITED", 429, True, "rejected"),
    ("ENCRYPTION_REQUIRED", 403, True, "rejected"),
    ("X_SERVER_FAILURE", 503, False, "unknown"),
])
def test_provider_outcomes(rt, prepared, code, status, definitive, outcome):
    class Rejected(FixtureClient):
        def send(self, recipient, text):
            raise ProviderError(code, status, definitive)
    rt.provider_override = Rejected(rt.factory)
    assert send(rt, prepared, 1, key()) == outcome
    with rt.factory() as db:
        assert db.scalar(select(func.count()).select_from(Attempt)) == 1


def test_reply_sync_ignores_earlier_consent_and_deduplicates(rt, prepared):
    with rt.factory.begin() as db:
        db.add(FixtureMessage(recipient_id="fixture_test", sender_id="fixture_test",
                              text="I agree to one prototype test.", created=now() - timedelta(hours=1)))
    assert send(rt, prepared, 1, key()) == "sent"
    sync(rt, prepared)
    with rt.factory() as db:
        assert reply_state(db, db.get(Outreach, prepared)) == "Awaiting reply"
    with rt.factory.begin() as db:
        db.add(FixtureMessage(recipient_id="fixture_test", sender_id="fixture_test", text="Confirmed."))
    sync(rt, prepared)
    sync(rt, prepared)
    with rt.factory() as db:
        assert db.scalar(select(func.count()).select_from(DMEvent)) == 3
        assert reply_state(db, db.get(Outreach, prepared)) == "Needs attention"
    acknowledge(rt, prepared)
    with rt.factory() as db:
        assert reply_state(db, db.get(Outreach, prepared)) == "Handled"


def test_explicit_opt_out_suppresses_without_response(rt, prepared):
    send(rt, prepared, 1, key())
    with rt.factory.begin() as db:
        db.add(FixtureMessage(recipient_id="fixture_test", sender_id="fixture_test", text="STOP"))
    sync(rt, prepared)
    from app.models import Suppression
    with rt.factory() as db:
        assert db.get(Suppression, "fixture_test")
        assert db.scalar(select(func.count()).select_from(FixtureMessage)) == 2


def test_restart_stale_reservation_is_unknown(rt, prepared):
    with rt.factory.begin() as db:
        attempt = Attempt(outreach_id=prepared, request_key=key(), text="approved", payload_hash="hash",
                          started=now() - timedelta(minutes=5))
        db.add(attempt)
        db.flush()
        db.get(Outreach, prepared).send_status = "in_flight"
        db.get(Account, "fixture_sender").active_attempt = attempt.id
    recover_stale(rt)
    with rt.factory() as db:
        assert db.get(Outreach, prepared).send_status == "unknown"
        assert db.get(Account, "fixture_sender").active_attempt


def test_reconnect_keeps_duplicate_ledger(rt, prepared):
    send(rt, prepared, 1, key())
    with rt.factory.begin() as db:
        account = db.get(Account, "fixture_sender")
        account.connected = False
    with rt.factory.begin() as db:
        db.get(Account, "fixture_sender").connected = True
    assert create_outreach(rt, "fixture_test") == prepared
    with pytest.raises(DomainError):
        send(rt, prepared, 1, key())


@pytest.mark.postgres
def test_parallel_budget_reservation_respects_cap(rt):
    rt.settings.x_budget_usd = 0.1

    def run():
        try:
            reserve(rt.factory, rt.settings, "test", 75_000)
            return True
        except DomainError:
            return False
    with ThreadPoolExecutor(2) as executor:
        assert sum(executor.map(lambda _: run(), range(2))) == 1


def test_history_failure_never_sends(rt, prepared):
    class Incomplete(FixtureClient):
        calls = 0

        def events(self, recipient, cursor=None):
            raise ProviderError("RATE_LIMITED", 429, True)

        def send(self, recipient, text):
            self.calls += 1
    provider = Incomplete(rt.factory)
    rt.provider_override = provider
    with pytest.raises(DomainError) as error:
        send(rt, prepared, 1, key())
    assert error.value.code == "HISTORY_INCOMPLETE"
    assert provider.calls == 0
