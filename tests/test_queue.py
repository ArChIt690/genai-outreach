import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.errors import DomainError, ProviderError
from app.integrations.fixture import FixtureClient
from app.main import create_app
from app.models import Account, Attempt, FixtureMessage, Outreach, SearchResult, Workspace
from app.services.discovery import discover
from app.services.drafting import generate
from app.services.outreach import create_outreach, save_draft, suppress
from app.services.queue import Worker, enqueue, review_items, skip, tick, unqueue
from app.services.sending import send


@pytest.fixture
def op(rt):
    """Operator-approved policy: discovered people may be messaged after approval."""
    rt.settings.outreach_policy = "operator_approved"
    return rt


def drafted(rt, person):
    """An unapproved evidence-based draft at version 1 for a discovered person."""
    discover(rt, "robotics, embodied AI")
    oid = create_outreach(rt, "fixture_" + person)
    assert generate(rt, oid, 0, "test-session") == 1
    return oid


def row(rt, oid):
    with rt.factory() as db:
        return db.get(Outreach, oid)


def messages(rt):
    with rt.factory() as db:
        return db.scalar(select(func.count()).select_from(FixtureMessage))


def test_enqueue_then_tick_sends_once(op):
    oid = drafted(op, "ada")
    enqueue(op, oid, 1)
    queued = row(op, oid)
    assert queued.queued_at and len(queued.queue_key) >= 16 and queued.approved_hash
    assert tick(op) == "sent"
    sent = row(op, oid)
    assert (sent.send_status, sent.queued_at, sent.queue_key, sent.queue_note) == ("sent", None, None, None)
    assert messages(op) == 1
    assert tick(op) == "idle" and messages(op) == 1


def test_queue_waits_between_sends(op):
    first, second = drafted(op, "ada"), drafted(op, "mira")
    enqueue(op, first, 1)
    enqueue(op, second, 1)
    assert tick(op) == "sent"
    assert tick(op) == "held:PACING" and messages(op) == 1
    assert row(op, first).send_status == "sent" and row(op, second).queued_at
    op.settings.send_min_gap_seconds = 0
    assert tick(op) == "sent" and messages(op) == 2


def test_queue_stops_at_daily_limit(op):
    op.settings.daily_send_limit, op.settings.send_min_gap_seconds = 1, 0
    enqueue(op, drafted(op, "ada"), 1)
    enqueue(op, drafted(op, "mira"), 1)
    assert tick(op) == "sent"
    assert tick(op) == "held:DAILY_LIMIT" and messages(op) == 1


@pytest.mark.parametrize("change,code", [("paused", "SENDING_PAUSED"), ("disabled", "SENDING_DISABLED"),
                                         ("disconnected", "ACCOUNT_RECONNECT_REQUIRED")])
def test_paused_or_disabled_holds_queue(op, change, code):
    oid = drafted(op, "ada")
    enqueue(op, oid, 1)
    if change == "disabled":
        op.settings.send_enabled = False
    else:
        with op.factory.begin() as db:
            if change == "paused":
                db.get(Workspace, "main").paused = True
            else:
                db.get(Account, "fixture_sender").connected = False
    assert tick(op) == "held:" + code
    assert messages(op) == 0 and row(op, oid).queued_at


def test_queueing_is_allowed_while_sending_is_off(op):
    op.settings.send_enabled = False
    oid = drafted(op, "ada")
    enqueue(op, oid, 1)
    assert row(op, oid).queued_at


def test_enqueue_stale_version_is_refused(op):
    oid = drafted(op, "ada")
    save_draft(op, oid, 1, "Edited in another tab. Reply STOP to opt out.")
    with pytest.raises(DomainError) as e:
        enqueue(op, oid, 1)
    assert e.value.code == "APPROVAL_STALE"
    assert row(op, oid).queued_at is None and row(op, oid).approved_hash is None


def test_enqueue_refused_under_test_allowlist(rt):
    oid = drafted(rt, "ada")
    with pytest.raises(DomainError) as e:
        enqueue(rt, oid, 1)
    assert e.value.code == "RECIPIENT_NOT_ALLOWED"
    assert row(rt, oid).queued_at is None and row(rt, oid).approved_hash is None


def test_enqueue_refuses_suppressed_person(op):
    oid = drafted(op, "ada")
    suppress(op, "fixture_ada")
    with pytest.raises(DomainError) as e:
        enqueue(op, oid, 1)
    assert e.value.code == "DO_NOT_CONTACT" and row(op, oid).queued_at is None


def test_enqueue_twice_keeps_one_request_key(op):
    oid = drafted(op, "ada")
    enqueue(op, oid, 1)
    first = row(op, oid).queue_key
    enqueue(op, oid, 1)
    assert row(op, oid).queue_key == first


def test_suppressed_after_queueing_is_removed_not_sent(op):
    oid = drafted(op, "ada")
    enqueue(op, oid, 1)
    suppress(op, "fixture_ada")
    assert tick(op) == "blocked:DO_NOT_CONTACT"
    after = row(op, oid)
    assert (after.queued_at, after.queue_note, after.send_status) == (None, "DO_NOT_CONTACT", "not_sent")
    assert messages(op) == 0 and tick(op) == "idle"


def test_stop_reply_or_policy_switch_removes_from_queue(op):
    oid = drafted(op, "ada")
    enqueue(op, oid, 1)
    op.settings.outreach_policy = "test_allowlist"
    assert tick(op) == "blocked:RECIPIENT_NOT_ALLOWED"
    assert row(op, oid).queued_at is None and messages(op) == 0


def test_editing_a_queued_draft_takes_it_out_of_the_queue(op):
    oid = drafted(op, "ada")
    enqueue(op, oid, 1)
    save_draft(op, oid, 1, "A different message. Reply STOP to opt out.")
    assert row(op, oid).queued_at is None and row(op, oid).queue_key is None
    assert tick(op) == "idle" and messages(op) == 0


def test_x_refusal_moves_on_to_next(op):
    class Refusing(FixtureClient):
        def send(self, recipient, text):
            if recipient == "fixture_ada":
                raise ProviderError("DM_NOT_ALLOWED", 403, True)
            return super().send(recipient, text)
    op.provider_override = Refusing(op.factory)
    op.settings.send_min_gap_seconds = 0
    first, second = drafted(op, "ada"), drafted(op, "mira")
    enqueue(op, first, 1)
    enqueue(op, second, 1)
    assert tick(op) == "rejected"
    refused = row(op, first)
    assert (refused.send_status, refused.queued_at, refused.queue_note) == ("rejected", None, "DM_NOT_ALLOWED")
    assert tick(op) == "sent" and row(op, second).send_status == "sent"


def test_unknown_outcome_stops_the_queue(op):
    class Uncertain(FixtureClient):
        calls = 0

        def send(self, recipient, text):
            self.calls += 1
            raise ProviderError("X_NETWORK_UNCERTAIN")
    provider = Uncertain(op.factory)
    op.provider_override = provider
    op.settings.send_min_gap_seconds = 0
    first, second = drafted(op, "ada"), drafted(op, "mira")
    enqueue(op, first, 1)
    enqueue(op, second, 1)
    assert tick(op) == "unknown"
    assert tick(op) == "held:SENDER_BUSY" and tick(op) == "held:SENDER_BUSY"
    assert provider.calls == 1 and row(op, second).queued_at and row(op, first).queued_at is None


def test_restart_replays_same_key_without_second_dm(op):
    oid = drafted(op, "ada")
    enqueue(op, oid, 1)
    # The app dispatched the message and stopped before clearing the queue entry.
    assert send(op, oid, 1, row(op, oid).queue_key) == "sent"
    assert row(op, oid).queued_at
    assert tick(op) == "sent"
    assert messages(op) == 1 and row(op, oid).queued_at is None
    with op.factory() as db:
        assert db.scalar(select(func.count()).select_from(Attempt)) == 1


def test_history_failure_holds_and_moves_item_to_the_back(op):
    class NoHistory(FixtureClient):
        def events(self, recipient, cursor=None):
            if recipient == "fixture_ada":
                raise ProviderError("X_SERVER_FAILURE", 503)
            return super().events(recipient, cursor)
    op.provider_override = NoHistory(op.factory)
    op.settings.send_min_gap_seconds = 0
    first, second = drafted(op, "ada"), drafted(op, "mira")
    enqueue(op, first, 1)
    enqueue(op, second, 1)
    assert tick(op) == "held:HISTORY_INCOMPLETE"
    held = row(op, first)
    assert held.queued_at and held.queue_note == "HISTORY_INCOMPLETE" and messages(op) == 0
    assert tick(op) == "sent" and row(op, second).send_status == "sent"


def test_unqueue_returns_the_draft_to_review(op):
    oid = drafted(op, "ada")
    enqueue(op, oid, 1)
    with op.factory() as db:
        assert review_items(db) == []
    unqueue(op, oid)
    after = row(op, oid)
    assert (after.queued_at, after.queue_key, after.approved_hash) == (None, None, None)
    with op.factory() as db:
        assert [o.id for o, _, _ in review_items(db)] == [oid]
    assert tick(op) == "idle"


def test_skip_hides_from_review_and_new_draft_restores(op):
    oid = drafted(op, "ada")
    enqueue(op, oid, 1)
    skip(op, oid)
    after = row(op, oid)
    assert (after.skipped, after.queued_at, after.approved_hash) == (True, None, None)
    with op.factory() as db:
        assert review_items(db) == []
    assert tick(op) == "idle"
    save_draft(op, oid, 1, "A second look at this one. Reply STOP to opt out.", source_ids=["p_ada_1"])
    with op.factory() as db:
        assert [o.id for o, _, _ in review_items(db)] == [oid]


def test_skip_is_refused_after_a_send(op):
    oid = drafted(op, "ada")
    enqueue(op, oid, 1)
    assert tick(op) == "sent"
    with pytest.raises(DomainError) as e:
        skip(op, oid)
    assert e.value.code == "ALREADY_CONTACTED"


def test_review_items_order_and_membership(op):
    ada, mira = drafted(op, "ada"), drafted(op, "mira")
    empty = create_outreach(op, "fixture_news")
    with op.factory.begin() as db:
        for result in db.scalars(select(SearchResult)):
            result.ai_fit = {"fixture_ada": "strong", "fixture_mira": "possible"}.get(result.candidate_id)
    with op.factory() as db:
        items = review_items(db)
        assert [o.id for o, _, _ in items] == [ada, mira]
        assert [(person.handle, result.ai_fit) for _, person, result in items] == [
            ("ada_robotics", "strong"), ("mira_models", "possible")]
        assert empty not in [o.id for o, _, _ in items]
    enqueue(op, ada, 1)
    with op.factory() as db:
        assert [o.id for o, _, _ in review_items(db)] == [mira]


def test_worker_runs_with_the_app_and_stops_with_it(rt):
    settings = rt.settings.model_copy(update={"worker_enabled": True, "queue_tick_seconds": 3600})
    app = create_app(settings, rt.factory)
    with TestClient(app):
        worker = app.state.worker
        assert isinstance(worker, Worker) and worker.alive
    assert not worker.alive


def test_app_without_worker_setting_starts_none(rt):
    app = create_app(rt.settings, rt.factory)
    with TestClient(app):
        assert app.state.worker is None


def test_worker_step_survives_errors(op, monkeypatch):
    from app.services import queue

    def broken(rt):
        raise RuntimeError("database password=SECRET")
    monkeypatch.setattr(queue, "tick", broken)
    assert Worker(op).run_once() == "error:RuntimeError"
