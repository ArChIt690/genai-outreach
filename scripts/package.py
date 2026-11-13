"""Create a source archive without local secrets, caches or database artifacts."""
import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def main():
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=root.parent / "genai-outreach.zip")
    args = parser.parse_args()
    destination = args.output.resolve()
    excluded = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "runtime",
                "test-results", "playwright-report", "build", "dist"}
    with ZipFile(destination, "x", ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.is_symlink() or path.resolve() == destination:
                continue
            relative = path.relative_to(root)
            if any(part in excluded or part.endswith(".egg-info") for part in relative.parts):
                continue
            if path.name.startswith(".env") and path.name != ".env.example":
                continue
            if path.suffix in {".pyc", ".log", ".db"}:
                continue
            archive.write(path, Path(root.name) / relative)
    with ZipFile(destination) as archive:
        assert all(not n.endswith("/.env") for n in archive.namelist())
        assert archive.testzip() is None
        print("Verified source archive:", destination)
        print("Files:", len(archive.namelist()))


if __name__ == "__main__":
    main()
