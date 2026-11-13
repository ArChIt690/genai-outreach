from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.errors import DomainError
from app.models import Workspace


def make_database(url):
    engine = create_engine(url, pool_pre_ping=True, pool_size=10, max_overflow=10)
    return engine, sessionmaker(engine, expire_on_commit=False)


def workspace_lock(db):
    return db.execute(select(Workspace).where(Workspace.id == "main").with_for_update()).scalar_one()


def initialize_workspace(factory, mode):
    with factory.begin() as db:
        w = db.get(Workspace, "main")
        if w is None:
            db.add(Workspace(id="main", mode=mode))
        elif w.mode != mode:
            raise DomainError("MODE_MISMATCH", "Use a separate database for live and fixture modes.")
