"""Seed accounts: remember which seeds a search started from and how the model described them."""
from alembic import op
from sqlalchemy import text

revision = "0003"
down_revision = "0002"

COLUMNS = (("search_runs", "seed_handles", "JSON"), ("search_runs", "seed_summary", "TEXT"))


def apply(bind):
    """Safe to run on a database that already has these columns."""
    for table, column, kind in COLUMNS:
        bind.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {kind}"))


def upgrade():
    apply(op.get_bind())


def downgrade():
    bind = op.get_bind()
    for table, column, _ in COLUMNS:
        bind.execute(text(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {column}"))
