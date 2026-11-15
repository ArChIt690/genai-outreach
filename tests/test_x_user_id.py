"""The helper that shows an X account's numeric ID for TEST_RECIPIENT_IDS."""
import pytest

from app.errors import ProviderError
from app.integrations.fixture import FixtureClient
from app.models import Workspace
from app.services.runtime import Runtime
from scripts.x_user_id import main


def spend(rt):
    with rt.factory() as db:
        return db.get(Workspace, "main").spend_micros


@pytest.mark.parametrize("handle", ["ada_robotics", "@ada_robotics", "https://x.com/ada_robotics"])
def test_prints_the_numeric_id_and_the_env_line(rt, capsys, handle):
    assert main([handle], rt=rt) == 0
    out = capsys.readouterr().out
    assert "@ada_robotics" in out and "fixture_ada" in out
    assert "TEST_RECIPIENT_IDS=fixture_ada" in out
    assert "synthetic" in out.lower()


def test_unknown_handle_is_reported_plainly(rt, capsys):
    assert main(["nobody_here"], rt=rt) == 1
    out = capsys.readouterr().out
    assert "nobody_here" in out and "Traceback" not in out


def test_bad_input_is_refused_without_calling_x(rt, capsys):
    class NoCalls(FixtureClient):
        def user(self, handle):
            pytest.fail("X was called for invalid input")
    rt.provider_override = NoCalls(rt.factory)
    assert main(["not a handle!"], rt=rt) == 1
    assert main([], rt=rt) == 2
    assert main(["a", "b"], rt=rt) == 2
    assert spend(rt) == 0


def test_live_mode_without_a_connected_account_says_what_to_do(rt, capsys):
    live = Runtime(rt.factory, rt.settings.model_copy(update={"app_mode": "live"}))
    assert main(["ada_robotics"], rt=live) == 1
    out = capsys.readouterr().out
    assert "Connect" in out and spend(rt) == 0


def test_x_refusal_is_reported_by_code(rt, capsys):
    class Refusing(FixtureClient):
        def user(self, handle):
            raise ProviderError("X_CREDITS_REQUIRED", 402, True)
    rt.provider_override = Refusing(rt.factory)
    assert main(["ada_robotics"], rt=rt) == 1
    assert "X_CREDITS_REQUIRED" in capsys.readouterr().out
