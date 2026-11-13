import secrets
from datetime import timedelta

from sqlalchemy import select

from app.errors import ProviderError
from app.integrations.fixture import FixtureClient
from app.models import FixtureMessage, Outreach, Suppression, now
from app.services.discovery import discover
from app.services.drafting import generate
from app.services.outreach import approve, create_outreach
from app.services.queue import Worker, sync_all, sync_due
from app.services.sending import send
from app.services.synchronization import reply_state


def key():
    return secrets.token_urlsafe(24)


def reply(rt, recipient, text):
    with rt.factory.begin() as db:
        db.add(FixtureMessage(recipient_id=recipient, sender_id=recipient, text=text))


def state(rt, oid):
    with rt.factory() as db:
        return reply_state(db, db.get(Outreach, oid))


def sent_to(rt, person):
    discover(rt, "robotics, embodied AI")
    oid = create_outreach(rt, "fixture_" + person)
    generate(rt, oid, 0, "test-session")
    approve(rt, oid, 1)
    assert send(rt, oid, 1, key()) == "sent"
    return oid


def test_sync_due_picks_up_a_reply(rt, prepared):
    assert send(rt, prepared, 1, key()) == "sent"
    reply(rt, "fixture_test", "Confirmed, thanks.")
    assert sync_due(rt) == 1
    assert state(rt, prepared) == "Needs attention"


def test_sync_due_respects_interval(rt, prepared):
    send(rt, prepared, 1, key())
    assert sync_due(rt) == 1
    reply(rt, "fixture_test", "A later reply.")
    assert sync_due(rt) == 0
    assert state(rt, prepared) == "Awaiting reply"
    with rt.factory.begin() as db:
        db.get(Outreach, prepared).last_sync = now() - timedelta(minutes=181)
    assert sync_due(rt) == 1 and state(rt, prepared) == "Needs attention"


def test_sync_due_off_when_zero(rt, prepared):
    rt.settings.auto_sync_minutes = 0
    send(rt, prepared, 1, key())
    assert sync_due(rt) == 0


def test_sync_due_ignores_unsent_messages(rt, prepared):
    assert sync_due(rt) == 0


def test_sync_due_ignores_sends_older_than_14_days(rt, prepared):
    send(rt, prepared, 1, key())
    with rt.factory.begin() as db:
        db.get(Outreach, prepared).sent_at = now() - timedelta(days=15)
    assert sync_due(rt) == 0


def test_sync_due_records_an_opt_out(rt, prepared):
    send(rt, prepared, 1, key())
    reply(rt, "fixture_test", "STOP")
    sync_due(rt)
    with rt.factory() as db:
        assert db.get(Suppression, "fixture_test")


def test_sync_due_waits_the_interval_after_a_failure_too(rt, prepared):
    class Down(FixtureClient):
        calls = 0

        def events(self, recipient, cursor=None):
            self.calls += 1
            raise ProviderError("X_SERVER_FAILURE", 503)
    send(rt, prepared, 1, key())
    provider = Down(rt.factory)
    rt.provider_override = provider
    assert sync_due(rt) == 1
    assert sync_due(rt) == 0 and provider.calls == 1
    with rt.factory() as db:
        assert db.get(Outreach, prepared).sync_error


def test_sync_all_counts_failures_and_continues(rt):
    class AdaDown(FixtureClient):
        def events(self, recipient, cursor=None):
            if recipient == "fixture_ada":
                raise ProviderError("X_SERVER_FAILURE", 503)
            return super().events(recipient, cursor)
    rt.settings.outreach_policy, rt.settings.send_min_gap_seconds = "operator_approved", 0
    ada, mira = sent_to(rt, "ada"), sent_to(rt, "mira")
    reply(rt, "fixture_mira", "Happy to chat.")
    rt.provider_override = AdaDown(rt.factory)
    assert sync_all(rt) == (1, 1)
    assert state(rt, mira) == "Needs attention"
    with rt.factory() as db:
        assert db.get(Outreach, ada).sync_error


def test_sync_all_with_nothing_sent(rt):
    assert sync_all(rt) == (0, 0)


def test_worker_step_also_checks_replies(rt, prepared):
    send(rt, prepared, 1, key())
    reply(rt, "fixture_test", "Got it.")
    assert Worker(rt).run_once() == "idle"
    assert state(rt, prepared) == "Needs attention"
    with rt.factory() as db:
        assert db.scalar(select(Outreach.last_sync).where(Outreach.id == prepared))
