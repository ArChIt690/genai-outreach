"""Local content refresh and retention maintenance. Never sends a message."""
import argparse
from datetime import timedelta

from sqlalchemy import select

from app.config import Settings
from app.db import make_database, workspace_lock
from app.models import DMEvent, Evidence, now
from app.services.discovery import invalidate_source, revalidate
from app.services.runtime import Runtime


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["refresh", "expire"])
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()
    settings = Settings()
    engine, factory = make_database(settings.database_url)
    runtime = Runtime(factory, settings)
    try:
        if args.action == "refresh":
            with factory() as db:
                ids = list(db.scalars(select(Evidence.id).where(Evidence.available.is_(True))))
            for offset in range(0, len(ids), 3):
                try:
                    revalidate(runtime, ids[offset:offset + 3])
                except Exception as error:
                    # Deliberately redact provider details; refresh changes already committed remain valid.
                    print(getattr(error, "code", "REFRESH_FAILED"))
        else:
            if args.days < 1:
                raise SystemExit("Retention must be at least one day.")
            cutoff = now() - timedelta(days=args.days)
            with factory.begin() as db:
                workspace_lock(db)
                for evidence in db.scalars(select(Evidence).where(Evidence.retrieved < cutoff)):
                    invalidate_source(db, evidence.id)
                    evidence.text, evidence.available, evidence.content_hash = "", False, ""
                for event in db.scalars(select(DMEvent).where(DMEvent.created < cutoff)):
                    event.text = ""
            print("Expired local source/reply bodies; retained contact history.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
