import os
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import expect, sync_playwright

from app.main import create_app
from conftest import TEST_PASSWORD


@pytest.mark.browser
def test_operator_browser_workflow(rt):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    rt.settings.app_origin = f"http://127.0.0.1:{port}"
    app = create_app(rt.settings, rt.factory)
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", access_log=False))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(.05)
    assert server.started
    screenshots = Path("docs/screenshots")
    screenshots.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as p:
            executable = os.environ.get("BROWSER_EXECUTABLE")
            if not executable and os.name == "nt":
                edge = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
                if edge.exists():
                    executable = str(edge)
            browser = p.chromium.launch(headless=True, executable_path=executable)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(rt.settings.app_origin + "/login")
            page.get_by_label("Operator password").fill(TEST_PASSWORD)
            page.get_by_role("button", name="Open workbench").click()
            expect(page.get_by_role("heading", name="Find people worth knowing.")).to_be_visible()
            page.get_by_role("button", name="Find relevant people").click()
            expect(page.get_by_role("link", name="Ada Tan", exact=True)).to_be_visible()
            page.screenshot(path=str(screenshots / "discover.png"), full_page=True)
            page.get_by_role("link", name="Ada Tan", exact=True).click()
            page.get_by_role("button", name="Prepare message", exact=True).click()
            page.get_by_role("button", name="Draft from evidence").click()
            expect(page.get_by_label("Exact message text")).to_contain_text("your public post says:")
            page.get_by_role("button", name="Approve version 1").click()
            expect(page.get_by_role("button", name="Simulate approved send")).to_be_disabled()
            page.screenshot(path=str(screenshots / "evidence-review.png"), full_page=True)
            page.get_by_role("link", name="Settings", exact=False).first.click()
            page.get_by_label("X handle", exact=True).fill("test_recipient")
            page.get_by_label("Consent reference").fill("Controlled synthetic test account")
            page.get_by_label("I control this recipient account").check()
            page.get_by_role("button", name="Record test consent").click()
            page.get_by_role("button", name="Prepare message", exact=True).click()
            page.get_by_label("Exact message text").fill(
                "As agreed, this is one prototype test message. Can you confirm receipt? Reply STOP to opt out.")
            page.get_by_label("This is a manually written message").check()
            page.get_by_role("button", name="Save draft", exact=True).click()
            page.get_by_role("button", name="Approve version 1").click()
            page.get_by_role("button", name="Simulate approved send").click()
            expect(page.get_by_text("Immutable submitted text")).to_be_visible()
            page.get_by_role("button", name="Add fixture reply").click()
            page.get_by_role("button", name="Sync replies", exact=True).click()
            expect(page.get_by_text("Needs attention", exact=True)).to_be_visible()
            page.screenshot(path=str(screenshots / "conversation.png"), full_page=True)
            page.get_by_role("link", name="Activity", exact=False).first.click()
            expect(page.get_by_role("cell", name="sent", exact=True)).to_be_visible()
            page.set_viewport_size({"width": 390, "height": 844})
            page.goto(rt.settings.app_origin + "/discover")
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.screenshot(path=str(screenshots / "mobile.png"), full_page=True)
            assert not errors
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        sock.close()
