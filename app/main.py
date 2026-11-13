import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select, text

from app.config import Settings
from app.db import initialize_workspace, make_database
from app.errors import DomainError, ProviderError
from app.integrations.llm import ai_ready, model_name, provider_label
from app.models import (Account, AICall, Attempt, Candidate, Consent, DMEvent, Evidence, Outreach, SearchResult,
                        SearchRun, Workspace)
from app.routes import actions, oauth
from app.security import session_for
from app.services.outreach import eligibility
from app.services.fit import fit_rank
from app.services.queue import HOLD_CODES, Worker, hold_reason, queued_items, review_items
from app.services.runtime import Runtime
from app.services.synchronization import recover_stale, reply_state

HERE = Path(__file__).parent
templates = Jinja2Templates(directory=HERE / "templates")


def create_app(settings=None, factory=None):
    settings = settings or Settings()
    engine = None
    if factory is None:
        engine, factory = make_database(settings.database_url)
    runtime = Runtime(factory, settings)

    @asynccontextmanager
    async def lifespan(app):
        initialize_workspace(factory, settings.app_mode)
        if settings.app_mode == "fixture":
            with factory.begin() as db:
                if db.get(Account, "fixture_sender") is None:
                    db.add(Account(x_id="fixture_sender", handle="prototype_operator"))
        recover_stale(runtime)
        if settings.worker_enabled:
            app.state.worker = Worker(runtime)
            app.state.worker.start()
        yield
        if app.state.worker:
            app.state.worker.stop()
        if engine:
            engine.dispose()

    app = FastAPI(title="GenAI outreach workbench", lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings, app.state.factory, app.state.runtime = settings, factory, runtime
    app.state.worker = None
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    app.include_router(actions.router)
    app.include_router(oauth.router)

    @app.middleware("http")
    async def headers(request, call_next):
        if request.headers.get("content-length", "").isdigit() and int(request.headers["content-length"]) > 32768:
            return JSONResponse({"code": "BODY_TOO_LARGE"}, status_code=413)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self'; "
            "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        response.headers["X-Frame-Options"] = "DENY"
        return response

    def render(request, name, **context):
        operator = session_for(request)
        with factory() as db:
            w = db.get(Workspace, "main")
            account = db.scalar(select(Account).where(Account.connected.is_(True)))
            pending = db.scalar(select(func.count()).select_from(Outreach).where(
                Outreach.send_status == "not_sent", Outreach.draft != "", Outreach.queued_at.is_(None),
                Outreach.skipped.is_(False)))
            return templates.TemplateResponse(request=request, name=name, context={
                "operator": operator, "settings": settings, "workspace": w, "account": account,
                "pending_review": pending, "ai_on": ai_ready(settings), "ai_provider": provider_label(settings),
                "ai_model": model_name(settings),
                "notice": request.query_params.get("notice", "")[:180], **context,
            })

    @app.exception_handler(DomainError)
    async def domain_error(request, exc):
        if exc.code == "LOGIN_REQUIRED":
            return RedirectResponse("/login", status_code=303)
        return templates.TemplateResponse(request=request, name="error.html", status_code=exc.status,
                                          context={"code": exc.code, "message": exc.message, "settings": settings})

    @app.exception_handler(ProviderError)
    async def provider_error(request, exc):
        return templates.TemplateResponse(request=request, name="error.html", status_code=502, context={
            "code": exc.code, "message": "X could not complete this operation. Check account access, credits "
                                       "and recipient restrictions in Settings; no automatic resend occurred.",
            "settings": settings,
        })

    @app.get("/")
    def index():
        return RedirectResponse("/discover", status_code=303)

    @app.get("/login")
    def login(request: Request):
        token = secrets.token_urlsafe(32)
        response = templates.TemplateResponse(request=request, name="login.html", context={
            "csrf": token, "settings": settings, "configured": bool(settings.operator_password_hash),
        })
        response.set_cookie("login_csrf", token, httponly=True, samesite="lax", secure=settings.secure_cookie)
        return response

    @app.get("/healthz")
    def health():
        return {"status": "ok"}

    @app.get("/readyz")
    def ready():
        try:
            with factory() as db:
                db.execute(text("SELECT 1"))
            return {"status": "ready"}
        except Exception:
            return JSONResponse({"status": "not_ready"}, status_code=503)

    @app.get("/settings")
    def settings_page(request: Request):
        session_for(request)
        with factory() as db:
            consents = db.scalars(select(Consent)).all()
            calls = db.scalars(select(AICall).order_by(AICall.created.desc()).limit(20)).all()
            total, tokens, average = db.execute(select(
                func.count(), func.coalesce(func.sum(func.coalesce(AICall.input_tokens, 0)
                                                     + func.coalesce(AICall.output_tokens, 0)), 0),
                func.coalesce(func.avg(AICall.latency_ms), 0))).one()
            by_outcome = dict(db.execute(select(AICall.outcome, func.count()).group_by(AICall.outcome)).all())
        usage = {"calls": total, "tokens": int(tokens), "average_ms": round(average),
                 "failures": by_outcome.get("failed", 0), "fallbacks": by_outcome.get("fallback_model", 0)}
        return render(request, "settings.html", consents=consents, calls=calls, usage=usage)

    @app.get("/discover")
    def discovery_page(request: Request):
        session_for(request)
        with factory() as db:
            run_id = request.query_params.get("run")
            run = db.get(SearchRun, run_id) if run_id else db.scalar(
                select(SearchRun).order_by(SearchRun.created.desc()).limit(1))
            results = db.execute(select(SearchResult, Candidate).join(
                Candidate, Candidate.x_id == SearchResult.candidate_id).where(
                SearchResult.run_id == run.id)).all() if run else []
            results = sorted(results, key=lambda r: (fit_rank(r[0].ai_fit), -r[0].score, r[1].handle))
        return render(request, "discover.html", run=run, results=results,
                      judged=any(r.ai_fit for r, _ in results))

    @app.get("/review")
    def review_page(request: Request):
        session_for(request)
        with factory() as db:
            w = db.get(Workspace, "main")
            cards = []
            for o, person, result in review_items(db):
                sender = db.get(Account, o.sender_id)
                evidence = [e for e in (db.get(Evidence, eid) for eid in o.selected_sources) if e]
                dates = {e.id: e.published for e in evidence}
                cards.append({
                    "outreach": o, "person": person, "result": result, "evidence": evidence,
                    "quotes": [{"text": q["quote"], "published": dates.get(q["source_id"])}
                               for q in (result.ai_quotes or [])] if result else [],
                    # Only reasons about this person disable the button; holds just make the queue wait.
                    "blocked": [r for r in eligibility(db, settings, w, sender, o, require_approval=False)
                                if r not in HOLD_CODES],
                })
            queued = queued_items(db)
            hold = hold_reason(db, settings) if queued else None
        return render(request, "review.html", cards=cards, queued=queued, hold=hold)

    @app.get("/candidates/{recipient}")
    def candidate_page(request: Request, recipient: str):
        session_for(request)
        recover_stale(runtime)
        with factory() as db:
            person = db.get(Candidate, recipient)
            if person is None:
                raise DomainError("NOT_FOUND", "This person has not been discovered or registered.", 404)
            account = db.scalar(select(Account).where(Account.connected.is_(True)))
            o = db.scalar(select(Outreach).where(Outreach.recipient_id == recipient,
                                                 Outreach.sender_id == account.x_id)) if account else None
            evidence = db.scalars(select(Evidence).where(Evidence.candidate_id == recipient)
                                  .order_by(Evidence.retrieved.desc()).limit(3)).all()
            score = db.scalar(select(SearchResult).where(SearchResult.candidate_id == recipient)
                              .order_by(SearchResult.score.desc()))
            reasons = eligibility(db, settings, db.get(Workspace, "main"), account, o) if o and account else []
            events = db.scalars(select(DMEvent).where(DMEvent.recipient_id == recipient,
                                                       DMEvent.account_id == account.x_id)
                                .order_by(DMEvent.created)).all() if account else []
            consent = db.scalar(select(Consent).where(Consent.recipient_id == recipient,
                                                       Consent.sender_id == account.x_id)) if account else None
            state = reply_state(db, o) if o else ""
            attempts = db.scalars(select(Attempt).where(Attempt.outreach_id == o.id)
                                 .order_by(Attempt.started.desc())).all() if o else []
        return render(request, "candidate.html", person=person, outreach=o, evidence=evidence, score=score,
                      reasons=reasons, events=events, consent=consent, reply_state=state,
                      attempts=attempts, request_key=secrets.token_urlsafe(24))

    @app.get("/activity")
    def activity_page(request: Request):
        session_for(request)
        recover_stale(runtime)
        with factory() as db:
            rows = []
            queued = [o.id for o, _ in queued_items(db)]
            hold = hold_reason(db, settings) if queued else None
            for o, p in db.execute(select(Outreach, Candidate).join(
                    Candidate, Candidate.x_id == Outreach.recipient_id).order_by(Outreach.id)):
                state = reply_state(db, o)
                if request.query_params.get("attention") and state != "Needs attention" and \
                        o.send_status not in {"unknown", "rejected"} and not o.sync_error and \
                        not (o.queue_note and not o.queued_at):
                    continue
                rows.append((o, p, state, queued.index(o.id) + 1 if o.id in queued else 0))
        return render(request, "activity.html", rows=rows, queue_total=len(queued), hold=hold)

    @app.get("/privacy")
    def privacy_page(request: Request):
        return templates.TemplateResponse(request=request, name="privacy.html", context={"settings": settings})

    return app
