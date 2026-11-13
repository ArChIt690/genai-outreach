import sys
from pathlib import Path

from cryptography.fernet import Fernet
from dotenv import dotenv_values

from app.security import verify_password
from scripts import bootstrap


def test_bootstrap_generates_secrets_without_printing_them(tmp_path, monkeypatch, capsys):
    example = Path(".env.example").read_text(encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    Path(".env.example").write_text(example, encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["bootstrap", "--fixture-demo"])
    monkeypatch.setattr(bootstrap.getpass, "getpass", lambda _: "setup-test-password-only")
    bootstrap.main()
    config = dotenv_values(".env")
    assert verify_password(config["OPERATOR_PASSWORD_HASH"], "setup-test-password-only")
    Fernet(config["TOKEN_ENCRYPTION_KEY"].encode())
    assert config["SEND_ENABLED"] == "true"
    output = capsys.readouterr().out
    assert "setup-test-password-only" not in output
    assert config["TOKEN_ENCRYPTION_KEY"] not in output


def test_bootstrap_never_overwrites_existing_configuration(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path(".env").write_text("X_CLIENT_ID=keep-this\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["bootstrap"])
    import pytest
    with pytest.raises(SystemExit, match="already exists"):
        bootstrap.main()
    assert dotenv_values(".env")["X_CLIENT_ID"] == "keep-this"
