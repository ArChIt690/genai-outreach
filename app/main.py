import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, text

from app.config import Settings
from app.db import initialize_workspace, make_database
from app.errors import DomainError, ProviderError
from app.models import Account, Attempt, Candidate, Consent, DMEvent, Evidence, Outreach, SearchResult, SearchRun, Workspace
from app.routes import actions, oauth
from app.security import session_for
from app.services.outreach import eligibility
from app.services.queue import Worker
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
            return templates.TemplateResponse(request=request, name=name, context={
                "operator": operator, "settings": settings, "workspace": w, "account": account,
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
        return render(request, "settings.html", consents=consents)

    @app.get("/discover")
    def discovery_page(request: Request):
        session_for(request)
        with factory() as db:
            run_id = request.query_params.get("run")
            run = db.get(SearchRun, run_id) if run_id else db.scalar(
                select(SearchRun).order_by(SearchRun.created.desc()).limit(1))
            results = db.execute(select(SearchResult, Candidate).join(
                Candidate, Candidate.x_id == SearchResult.candidate_id).where(
                SearchResult.run_id == run.id).order_by(SearchResult.score.desc())) .all() if run else []
        return render(request, "discover.html", run=run, results=results)

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
            for o, p in db.execute(select(Outreach, Candidate).join(
                    Candidate, Candidate.x_id == Outreach.recipient_id).order_by(Outreach.id)):
                state = reply_state(db, o)
                if request.query_params.get("attention") and state != "Needs attention" and \
                        o.send_status not in {"unknown", "rejected"} and not o.sync_error:
                    continue
                rows.append((o, p, state))
        return render(request, "activity.html", rows=rows)

    @app.get("/privacy")
    def privacy_page(request: Request):
        return templates.TemplateResponse(request=request, name="privacy.html", context={"settings": settings})

    return app
