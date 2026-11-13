"""Assisted outreach: AI call log, AI fit fields, send queue fields."""
from alembic import op
from sqlalchemy import text

from app.models import Base

revision = "0002"
down_revision = "0001"

COLUMNS = (
    ("search_results", "ai_fit", "VARCHAR(12)"),
    ("search_results", "ai_role", "VARCHAR(20)"),
    ("search_results", "ai_reason", "TEXT"),
    ("search_results", "ai_quotes", "JSON"),
    ("outreach", "skipped", "BOOLEAN NOT NULL DEFAULT false"),
    ("outreach", "queued_at", "TIMESTAMP WITH TIME ZONE"),
    ("outreach", "queue_key", "VARCHAR(80)"),
    ("outreach", "queue_note", "VARCHAR(80)"),
)


def apply(bind):
    """Safe to run on a database that already has some or all of these changes."""
    Base.metadata.create_all(bind)
    for table, column, kind in COLUMNS:
        bind.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {kind}"))


def upgrade():
    apply(op.get_bind())


def downgrade():
    bind = op.get_bind()
    for table, column, _ in COLUMNS:
        bind.execute(text(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {column}"))
    bind.execute(text("DROP TABLE IF EXISTS ai_calls"))
