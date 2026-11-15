import secrets

import pytest

from app.errors import DomainError
from app.services.discovery import discover
from app.services.drafting import generate
from app.services.outreach import approve, create_outreach, save_draft, suppress
from app.services.sending import send


def key():
    return secrets.token_urlsafe(24)


def discovered(rt):
    """A person found by search, with an approved evidence-based draft at version 1."""
    discover(rt, "robotics, embodied AI")
    oid = create_outreach(rt, "fixture_ada")
    generate(rt, oid, 0, "test-session")
    approve(rt, oid, 1)
    return oid


def test_default_policy_blocks_discovered_people(rt):
    oid = discovered(rt)
    with pytest.raises(DomainError) as e:
        send(rt, oid, 1, key())
    assert e.value.code == "RECIPIENT_NOT_ALLOWED"


def test_operator_approved_sends_to_discovered_person(rt):
    rt.settings.outreach_policy = "operator_approved"
    assert send(rt, discovered(rt), 1, key()) == "sent"


def test_operator_approved_still_honours_do_not_contact(rt):
    rt.settings.outreach_policy = "operator_approved"
    oid = discovered(rt)
    suppress(rt, "fixture_ada")
    with pytest.raises(DomainError) as e:
        send(rt, oid, 1, key())
    assert e.value.code == "DO_NOT_CONTACT"


def test_operator_approved_still_needs_approval(rt):
    rt.settings.outreach_policy = "operator_approved"
    discover(rt, "robotics, embodied AI")
    oid = create_outreach(rt, "fixture_ada")
    generate(rt, oid, 0, "test-session")
    with pytest.raises(DomainError) as e:
        send(rt, oid, 1, key())
    assert e.value.code == "APPROVAL_STALE"


def test_operator_approved_test_message_still_needs_consent(rt):
    rt.settings.outreach_policy = "operator_approved"
    discover(rt, "robotics")
    oid = create_outreach(rt, "fixture_ada")
    with pytest.raises(DomainError) as e:
        save_draft(rt, oid, 0, "Test.", test_message=True)
    assert e.value.code == "CONSENT_REQUIRED"
