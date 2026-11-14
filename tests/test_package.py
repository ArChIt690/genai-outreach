from zipfile import ZipFile

import pytest

from scripts.package import build, filled_secrets


def tree(root, files):
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def test_archive_leaves_out_secrets_and_working_notes(tmp_path):
    root = tmp_path / "project"
    tree(root, {
        "README.md": "readme", "app/main.py": "print()", ".env": "GEMINI_API_KEY=real",
        ".env.example": "GEMINI_API_KEY=\nDRAFT_PROVIDER=template\n",
        "docs/ARCHITECTURE.md": "kept", "docs/superpowers/specs/design.md": "working notes",
        ".superpowers/sdd/progress.md": "ledger", ".claude/settings.local.json": "{}",
        "demo.mp4": "video", "app/__pycache__/main.pyc": "cache",
    })
    destination = tmp_path / "out.zip"
    build(root, destination)
    with ZipFile(destination) as archive:
        names = {n.split("/", 1)[1] for n in archive.namelist()}
    assert names == {"README.md", "app/main.py", ".env.example", "docs/ARCHITECTURE.md"}


def test_archive_is_refused_when_the_template_holds_a_secret(tmp_path):
    root = tmp_path / "project"
    tree(root, {"README.md": "readme", ".env.example": 'X_CLIENT_ID=\nGEMINI_API_KEY="abc123"\n'})
    destination = tmp_path / "out.zip"
    with pytest.raises(SystemExit) as error:
        build(root, destination)
    assert "GEMINI_API_KEY" in str(error.value) and "abc123" not in str(error.value)
    assert not destination.exists()


def test_filled_secrets_names_only_secret_like_keys():
    template = ("APP_MODE=fixture\n# ANTHROPIC_API_KEY=commented\nOPERATOR_PASSWORD_HASH=\n"
                "TOKEN_ENCRYPTION_KEY=abc\nX_CLIENT_SECRET='s'\nGEMINI_API_KEY=\nX_CLIENT_ID=public-id\n")
    assert filled_secrets(template) == ["TOKEN_ENCRYPTION_KEY", "X_CLIENT_SECRET"]


def test_archive_leaves_out_the_brief_and_the_private_guide(tmp_path):
    root = tmp_path / "project"
    tree(root, {"README.md": "readme", "PROJECT_GUIDE.md": "notes for the candidate",
                "Take-Home Assignment.pdf": "the fund's brief", ".env.example": "GEMINI_API_KEY=\n"})
    destination = tmp_path / "out.zip"
    build(root, destination)
    with ZipFile(destination) as archive:
        assert {n.split("/", 1)[1] for n in archive.namelist()} == {"README.md", ".env.example"}
