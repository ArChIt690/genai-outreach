from app.db import workspace_lock
from app.errors import DomainError
from app.models import Usage


def reserve(factory, settings, kind, micros, model=False):
    with factory.begin() as db:
        w = workspace_lock(db)
        attr = "model_spend_micros" if model else "spend_micros"
        limit = settings.model_budget_usd if model else settings.x_budget_usd
        if getattr(w, attr) + micros > round(limit * 1_000_000):
            raise DomainError("BUDGET_EXCEEDED", "The configured usage allowance is exhausted.")
        setattr(w, attr, getattr(w, attr) + micros)
        row = Usage(kind=kind, reserved_micros=micros)
        db.add(row)
        db.flush()
        return row.id


def settle(factory, usage_id, actual_micros, model=False):
    with factory.begin() as db:
        w = workspace_lock(db)
        row = db.get(Usage, usage_id)
        if row.settled_micros is not None:
            return
        # Never charge less than zero or silently exceed a reservation.
        actual = max(0, actual_micros)
        attr = "model_spend_micros" if model else "spend_micros"
        setattr(w, attr, getattr(w, attr) + actual - row.reserved_micros)
        row.settled_micros = actual
