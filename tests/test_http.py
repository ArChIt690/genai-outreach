import re
from datetime import timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.errors import DomainError, ProviderError
from app.integrations.x_client import XClient
from app.main import create_app
from app.models import Account, OperatorSession, Outreach, now
from app.security import digest, new_session
from app.services.runtime import Runtime
from conftest import TEST_PASSWORD


@pytest.fixture
def client(rt):
    app = create_app(rt.settings, rt.factory)
    with TestClient(app) as client:
        yield client


def sign_in(client):
    page = client.get("/login")
    csrf = re.search(r'name="csrf" value="([^"]+)"', page.text)[1]
    response = client.post("/login", data={"csrf": csrf, "password": TEST_PASSWORD}, follow_redirects=False)
    assert response.status_code == 303
    return response


def test_login_and_csrf(client):
    assert client.get("/discover", follow_redirects=False).headers["location"] == "/login"
    sign_in(client)
    page = client.get("/discover")
    assert page.status_code == 200
    assert "Synthetic workspace" in page.text
    response = client.post("/searches", data={"topics": "robotics"})
    assert response.status_code == 403
    csrf = re.search(r'name="csrf" value="([^"]+)"', page.text)[1]
    assert client.post("/searches", data={"topics": "robotics", "csrf": csrf},
                       headers={"origin": "https://attacker.example"}).status_code == 403
    response = client.post("/searches", data={"topics": "robotics", "csrf": csrf})
    assert response.status_code == 200
    assert "Ada Tan" in response.text
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_live_configuration_never_falls_back_to_fixtures(rt):
    settings = rt.settings.model_copy(update={"app_mode": "live"})
    runtime = Runtime(rt.factory, settings)
    with pytest.raises(DomainError) as error:
        runtime.read("search", "robotics")
    assert error.value.code == "ACCOUNT_RECONNECT_REQUIRED"


def test_mode_database_mismatch(rt):
    from app.db import initialize_workspace
    with pytest.raises(DomainError):
        initialize_workspace(rt.factory, "live")


@pytest.mark.parametrize("status,definitive", [(401, True), (429, True), (408, False), (500, False)])
def test_x_send_is_not_retried_and_redacts_errors(status, definitive):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"detail": "do not expose credential: SECRET"})
    client = XClient("TEST_SECRET", httpx.MockTransport(handler))
    try:
        with pytest.raises(ProviderError) as error:
            client.send("123", "approved text")
        assert len(calls) == 1
        assert error.value.definitive is definitive
        assert "SECRET" not in str(error.value)
        assert calls[0].url.path == "/2/dm_conversations/with/123/messages"
    finally:
        client.close()


def test_x_adapter_parameters_and_success():
    calls = []

    def handler(request):
        calls.append(request)
        if request.method == "POST":
            return httpx.Response(201, json={"data": {"dm_event_id": "99", "dm_conversation_id": "c1"}})
        return httpx.Response(200, json={"data": [], "meta": {"result_count": 0}})
    client = XClient("TEST_ONLY", httpx.MockTransport(handler))
    try:
        client.search('"robotics"')
        client.events("123", "cursor")
        assert calls[0].url.params["max_results"] == "50"
        assert calls[0].url.params["expansions"] == "author_id"
        assert calls[1].url.params["pagination_token"] == "cursor"
        assert client.send("123", "approved")["dm_event_id"] == "99"
    finally:
        client.close()


def test_expired_session_and_oauth_state(client, rt):
    token = new_session(rt.factory, 1)
    with rt.factory.begin() as db:
        db.get(OperatorSession, digest(token)).expires = now() - timedelta(seconds=1)
    client.cookies.set("operator", token)
    assert client.get("/settings", follow_redirects=False).headers["location"] == "/login"
    sign_in(client)
    assert client.get("/oauth/x/start").status_code == 409


def test_oauth_invalid_and_replayed_state(rt, monkeypatch):
    import app.routes.oauth as oauth_module
    settings = rt.settings.model_copy(update={"app_mode": "live", "x_client_id": "test-client"})
    # Same test schema only for this HTTP state-validation test; no API requests.
    app = create_app(settings, rt.factory)
    token = new_session(rt.factory, 1)
    with TestClient(create_app(rt.settings, rt.factory)) as client:
        # Use the live OAuth router with the fixture DB, without executing a live-mode startup.
        client.app.state.settings = settings
        client.cookies.set("operator", token)
        redirect = client.get("/oauth/x/start", follow_redirects=False)
        assert redirect.status_code == 303
        from urllib.parse import parse_qs, urlsplit
        state = parse_qs(urlsplit(redirect.headers["location"]).query)["state"][0]
        assert client.get("/oauth/x/callback?code=test&state=wrong").status_code == 403

        def fail(*args, **kwargs):
            raise httpx.ConnectError("redacted")
        monkeypatch.setattr(oauth_module.httpx, "post", fail)
        assert client.get("/oauth/x/callback", params={"code": "test", "state": state}).status_code == 409
        assert client.get("/oauth/x/callback", params={"code": "test", "state": state}).status_code == 403
    assert app is not None


@pytest.mark.parametrize("payload", [
    {"data": [], "errors": [{"detail": "incomplete"}]},
    {"data": [{"id": "x", "created_at": now().isoformat()}]},
    {"meta": {}},
])
def test_incomplete_history_blocks_send(rt, prepared, payload):
    from app.integrations.fixture import FixtureClient
    from app.services.sending import send

    class Broken(FixtureClient):
        def events(self, recipient, cursor=None):
            return payload
    rt.provider_override = Broken(rt.factory)
    with pytest.raises(DomainError) as error:
        send(rt, prepared, 1, "request-key-long-enough")
    assert error.value.code == "HISTORY_INCOMPLETE"


def test_disconnected_account_preserves_ledger(client, rt, prepared):
    sign_in(client)
    page = client.get("/settings")
    csrf = re.search(r'name="csrf" value="([^"]+)"', page.text)[1]
    assert client.post("/settings/disconnect", data={"csrf": csrf}).status_code == 200
    with rt.factory() as db:
        assert not db.get(Account, "fixture_sender").connected
        assert db.get(Outreach, prepared) is not None
        assert db.scalar(select(Account.x_id)) == "fixture_sender"
