"""Registering a test recipient that isn't on the test list yet tells the operator its numeric X ID."""
import re

import pytest
from fastapi.testclient import TestClient

from app.errors import DomainError
from app.integrations.fixture import FixtureClient
from app.main import create_app
from app.services.outreach import registration
from app.services.runtime import Runtime
from conftest import TEST_PASSWORD


class LiveLike(FixtureClient):
    """Fixture data, but numeric ids as real X returns them."""
    def user(self, handle):
        if handle == "prototype_operator":
            return {"id": "fixture_sender", "username": "prototype_operator", "name": "Prototype operator"}
        profile = super().user(handle)
        profile["id"] = {"test_recipient": "1234567890123456789",
                         "ada_robotics": "1111111111111111111"}.get(handle, profile["id"])
        return profile


def live(rt, allowed=""):
    runtime = Runtime(rt.factory, rt.settings.model_copy(update={"app_mode": "live", "test_recipient_ids": allowed}))
    runtime.provider_override = LiveLike(rt.factory)
    return runtime


def test_unlisted_account_message_names_its_numeric_id(rt):
    with pytest.raises(DomainError) as e:
        registration(live(rt), "@test_recipient", "My own second account", True)
    assert e.value.code == "RECIPIENT_NOT_ALLOWED"
    assert "@test_recipient" in e.value.message and "1234567890123456789" in e.value.message
    assert "TEST_RECIPIENT_IDS=1234567890123456789" in e.value.message and "restart" in e.value.message


def test_message_keeps_ids_already_listed(rt):
    with pytest.raises(DomainError) as e:
        registration(live(rt, "999"), "test_recipient", "My own second account", True)
    assert "TEST_RECIPIENT_IDS=999,1234567890123456789" in e.value.message


def test_listed_account_registers(rt):
    assert registration(live(rt, "1234567890123456789"), "test_recipient", "My own second account", True) \
        == "1234567890123456789"


def test_sender_cannot_register_itself(rt):
    with pytest.raises(DomainError) as e:
        registration(live(rt, "fixture_sender"), "prototype_operator", "Me", True)
    assert e.value.code == "RECIPIENT_NOT_ALLOWED" and "sending account" in e.value.message
    assert "TEST_RECIPIENT_IDS" not in e.value.message


def test_synthetic_mode_points_to_the_synthetic_recipient(rt):
    with pytest.raises(DomainError) as e:
        registration(rt, "ada_robotics", "Synthetic", True)
    assert "test_recipient" in e.value.message and "TEST_RECIPIENT_IDS" not in e.value.message


def test_settings_page_shows_the_id_after_a_failed_registration(rt):
    from app.models import Workspace
    with rt.factory.begin() as db:
        db.get(Workspace, "main").mode = "live"
    settings = rt.settings.model_copy(update={"app_mode": "live"})
    app = create_app(settings, rt.factory)
    app.state.runtime.provider_override = LiveLike(rt.factory)
    with TestClient(app) as client:
        login = client.get("/login")
        client.post("/login", data={"csrf": re.search(r'name="csrf" value="([^"]+)"', login.text)[1],
                                    "password": TEST_PASSWORD})
        csrf = re.search(r'name="csrf" value="([^"]+)"', client.get("/settings").text)[1]
        page = client.post("/test-recipients", data={"csrf": csrf, "handle": "test_recipient",
                                                     "reference": "My own second account", "controlled": "on"})
    assert page.status_code == 409 and "TEST_RECIPIENT_IDS=1234567890123456789" in page.text
