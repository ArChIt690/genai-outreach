"""Create a source archive without local secrets, caches, working notes or database artifacts."""
import argparse
import re
import subprocess
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

EXCLUDED_PARTS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "runtime",
                  "test-results", "playwright-report", "build", "dist", ".superpowers", ".claude"}
EXCLUDED_PATHS = {("docs", "superpowers")}
EXCLUDED_SUFFIXES = {".pyc", ".log", ".db", ".mp4", ".mov", ".zip", ".pdf"}
# The candidate's own guide to the project is not part of the submission.
EXCLUDED_NAMES = {"PROJECT_GUIDE.md"}
SECRET_NAME = re.compile(r"^([A-Z0-9_]*(?:KEY|SECRET|HASH|TOKEN|PASSWORD)[A-Z0-9_]*)=(.*)$")


def filled_secrets(template: str) -> list[str]:
    """Names of secret-like settings in .env.example that have a value. They must all be blank."""
    names = []
    for line in template.splitlines():
        found = SECRET_NAME.match(line.strip())
        if found and found.group(2).strip().strip("'\""):
            names.append(found.group(1))
    return names


def candidates(root: Path) -> list[Path]:
    """Files tracked by git when root is a repository, so untracked notes and downloads never ship.
    Outside a repository, every file under root."""
    if (root / ".git").exists():
        listed = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True, check=True).stdout
        return sorted(root / name for name in listed.decode("utf-8").split("\0") if name)
    return sorted(root.rglob("*"))


def build(root: Path, destination: Path) -> int:
    template = root / ".env.example"
    if template.exists():
        filled = filled_secrets(template.read_text(encoding="utf-8"))
        if filled:
            raise SystemExit(".env.example holds values for: " + ", ".join(filled)
                             + ". Move them to .env and leave the template blank before packaging.")
    with ZipFile(destination, "x", ZIP_DEFLATED) as archive:
        for path in candidates(root):
            if not path.is_file() or path.is_symlink() or path.resolve() == destination:
                continue
            relative = path.relative_to(root)
            if any(part in EXCLUDED_PARTS or part.endswith(".egg-info") for part in relative.parts):
                continue
            if relative.parts[:2] in EXCLUDED_PATHS:
                continue
            if path.name.startswith(".env") and path.name != ".env.example":
                continue
            if path.suffix.lower() in EXCLUDED_SUFFIXES or path.name in EXCLUDED_NAMES:
                continue
            archive.write(path, Path(root.name) / relative)
    with ZipFile(destination) as archive:
        assert all(not n.endswith("/.env") for n in archive.namelist())
        assert archive.testzip() is None
        return len(archive.namelist())


def main():
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=root.parent / "genai-outreach.zip")
    args = parser.parse_args()
    destination = args.output.resolve()
    count = build(root, destination)
    print("Verified source archive:", destination)
    print("Files:", count)


if __name__ == "__main__":
    main()
