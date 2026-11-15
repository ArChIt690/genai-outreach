import os
from datetime import timedelta

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import text

from app.config import Settings
from app.db import initialize_workspace, make_database
from app.models import Account, Base, OperatorSession, now
from app.security import password_hash
from app.services.outreach import approve, create_outreach, registration, save_draft
from app.services.runtime import Runtime

TEST_PASSWORD = "test-only-browser-password"
# Real credentials in the developer's environment must never reach a test.
REAL_CREDENTIALS = ("OPENAI_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "X_CLIENT_ID", "X_CLIENT_SECRET",
                    "TOKEN_ENCRYPTION_KEY", "OPERATOR_PASSWORD_HASH")


@pytest.fixture(autouse=True)
def no_real_credentials(monkeypatch):
    for name in REAL_CREDENTIALS:
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.lower(), raising=False)


@pytest.fixture(scope="session")
def database():
    url = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://outreach@127.0.0.1:55432/outreach_test")
    if not url.rsplit("/", 1)[-1].startswith("outreach_test"):
        raise RuntimeError("Tests may only use a database named outreach_test...")
    engine, factory = make_database(url)
    Base.metadata.create_all(engine)
    yield engine, factory, url
    engine.dispose()


@pytest.fixture
def rt(database):
    engine, factory, url = database
    with engine.begin() as connection:
        tables = ", ".join('"' + t.name + '"' for t in reversed(Base.metadata.sorted_tables))
        connection.execute(text("TRUNCATE " + tables + " CASCADE"))
    settings = Settings(_env_file=None, database_url=url, send_enabled=True, worker_enabled=False,
                        history_limit_acknowledged=True, token_encryption_key=Fernet.generate_key().decode(),
                        operator_password_hash=password_hash(TEST_PASSWORD))
    initialize_workspace(factory, "fixture")
    with factory.begin() as db:
        db.add(Account(x_id="fixture_sender", handle="prototype_operator"))
        db.add(OperatorSession(token_hash="test-session", csrf="test-csrf",
                               expires=now() + timedelta(hours=1)))
    return Runtime(factory, settings)


@pytest.fixture
def prepared(rt):
    recipient = registration(rt, "test_recipient", "Controlled synthetic account consent", True)
    oid = create_outreach(rt, recipient)
    save_draft(rt, oid, 0, "This is our agreed prototype test. Can you confirm receipt? Reply STOP to opt out.",
               test_message=True)
    approve(rt, oid, 1)
    return oid
