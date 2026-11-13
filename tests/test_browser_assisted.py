import os
import socket
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import expect, sync_playwright
from sqlalchemy import func, select

from app.main import create_app
from app.models import FixtureMessage, Outreach
from app.services import drafting, fit
from app.services.queue import tick
from conftest import TEST_PASSWORD

JUDGMENTS = {"people": [
    {"candidate_id": "fixture_ada", "fit": "strong", "role": "researcher",
     "reason": "Building an open manipulation benchmark and has released its first evaluation scripts.",
     "quotes": [{"source_id": "p_ada_1", "quote": "I'm building an open robotics manipulation benchmark."}]},
    {"candidate_id": "fixture_mira", "fit": "possible", "role": "researcher",
     "reason": "Researches embodied AI and compares policies in simulation; no released project mentioned.",
     "quotes": [{"source_id": "p_mira", "quote": "I'm researching embodied AI."}]},
    {"candidate_id": "fixture_news", "fit": "weak", "role": "not_a_person",
     "reason": "A news account that reports on other people's work.", "quotes": []},
]}


def canned_draft(rt, kind, system, payload, max_tokens=4096):
    source_id, post = next(iter(payload["sources"].items()))
    first_name = payload["recipient"]["name"].split()[0]
    return {"draft_text": f"Hi {first_name}, I read your post about your recent work and wanted to say hello. "
                          f"I'm {payload['sender']}. Would you be open to a short chat? "
                          "Reply STOP and I won't message again.",
            "claims": [{"source_id": source_id, "quote": post[:30]}], "uncertainties": []}


@contextmanager
def served(rt):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    rt.settings.app_origin = f"http://127.0.0.1:{sock.getsockname()[1]}"
    server = uvicorn.Server(uvicorn.Config(create_app(rt.settings, rt.factory), log_level="warning",
                                           access_log=False))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(.05)
    assert server.started
    try:
        yield rt.settings.app_origin
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        sock.close()


@pytest.mark.browser
def test_assisted_outreach_browser_flow(rt, monkeypatch):
    rt.settings.outreach_policy, rt.settings.send_min_gap_seconds = "operator_approved", 0
    rt.settings.draft_provider, rt.settings.gemini_api_key = "gemini", "test-key"
    monkeypatch.setattr(fit, "complete_json", lambda *args, **kwargs: JUDGMENTS)
    monkeypatch.setattr(drafting, "complete_json", canned_draft)
    screenshots = Path("docs/screenshots")
    screenshots.mkdir(parents=True, exist_ok=True)
    with served(rt) as origin, sync_playwright() as p:
        executable = os.environ.get("BROWSER_EXECUTABLE")
        if not executable and os.name == "nt":
            edge = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
            if edge.exists():
                executable = str(edge)
        browser = p.chromium.launch(headless=True, executable_path=executable)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(origin + "/login")
        page.get_by_label("Operator password").fill(TEST_PASSWORD)
        page.get_by_role("button", name="Open workbench").click()
        page.get_by_role("button", name="Find relevant people").click()
        expect(page.get_by_text("Fit: strong · researcher")).to_be_visible()
        expect(page.get_by_text("Building an open manipulation benchmark")).to_be_visible()
        page.screenshot(path=str(screenshots / "discover-ai.png"), full_page=True)
        page.get_by_role("button", name="Draft for top matches").click()
        expect(page.get_by_role("heading", name="Review each message.")).to_be_visible()
        expect(page.get_by_text("2 drafted, 0 skipped")).to_be_visible()
        ada = page.get_by_role("article", name="Ada Tan")
        mira = page.get_by_role("article", name="Mira Nguyen")
        expect(ada.get_by_label("Exact message text")).to_contain_text("Hi Ada,")
        expect(ada.get_by_text("AI draft · gemini")).to_be_visible()
        expect(page.get_by_role("article", name="Robotics Daily")).to_have_count(0)
        page.screenshot(path=str(screenshots / "review.png"), full_page=True)
        for path in ("/review", "/activity", "/settings", "/discover"):
            page.set_viewport_size({"width": 390, "height": 844})
            page.goto(origin + path)
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), path
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.goto(origin + "/review")
        # Save an edit first, then approve the saved version.
        edited = "Hi Ada, your manipulation benchmark caught my eye. Open to a short chat? Reply STOP to opt out."
        ada.get_by_label("Exact message text").fill(edited)
        ada.get_by_role("button", name="Save edit").click()
        expect(ada.get_by_text("Version 2")).to_be_visible()
        expect(ada.get_by_text("Edited by you")).to_be_visible()
        ada.get_by_role("button", name="Approve and queue").click()
        expect(page.get_by_text("Approved and queued.")).to_be_visible()
        expect(page.get_by_role("article", name="Ada Tan")).to_have_count(0)
        # Edit and approve in one step: the text on screen is what gets approved.
        direct = "Hi Mira, your embodied AI experiments sound interesting. Open to a chat? Reply STOP to opt out."
        mira.get_by_label("Exact message text").fill(direct)
        mira.get_by_role("button", name="Approve and queue").click()
        expect(page.get_by_role("heading", name="Waiting to send")).to_be_visible()
        expect(page.get_by_text("Nothing is waiting for review.")).to_be_visible()
        assert tick(rt) == "sent" and tick(rt) == "sent" and tick(rt) == "idle"
        with rt.factory() as db:
            assert sorted(db.scalars(select(FixtureMessage.text))) == sorted([edited, direct])
            assert db.scalar(select(func.count()).select_from(Outreach).where(Outreach.send_status == "sent")) == 2
        page.get_by_role("link", name="Activity", exact=False).first.click()
        expect(page.get_by_role("cell", name="sent", exact=True)).to_have_count(2)
        page.get_by_role("button", name="Sync all now").click()
        expect(page.get_by_text("2 conversations checked.")).to_be_visible()
        page.goto(origin + "/settings")
        expect(page.get_by_role("heading", name="AI usage")).to_be_visible()
        expect(page.get_by_text("Operator-approved sending").first).to_be_visible()
        assert not errors
        browser.close()
