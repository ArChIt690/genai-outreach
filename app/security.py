import hashlib
import secrets
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.errors import DomainError
from app.models import OperatorSession, now


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password):
    return PasswordHasher().hash(password)


def verify_password(encoded, password):
    try:
        return PasswordHasher().verify(encoded, password)
    except (InvalidHashError, VerificationError):
        return False


def cipher(settings):
    if not settings.token_encryption_key:
        raise DomainError("SETUP_REQUIRED", "Generate a token encryption key with the bootstrap script.", 503)
    return Fernet(settings.token_encryption_key.encode())


def new_session(factory, hours):
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    with factory.begin() as db:
        db.add(OperatorSession(token_hash=digest(token), csrf=csrf, expires=now() + timedelta(hours=hours)))
    return token


def session_for(request):
    token = request.cookies.get("operator", "")
    with request.app.state.factory() as db:
        session = db.get(OperatorSession, digest(token))
        if session is None or session.expires <= now():
            raise DomainError("LOGIN_REQUIRED", "Sign in to continue.", 401)
        return session


def csrf_check(request, session, supplied):
    origin = request.headers.get("origin")
    if origin and origin != request.app.state.settings.app_origin:
        raise DomainError("ORIGIN_REJECTED", "This request came from a different website.", 403)
    if not secrets.compare_digest(session.csrf, str(supplied or "")):
        raise DomainError("CSRF_REJECTED", "Refresh the page and try again.", 403)


def locked_session(db, token_hash):
    return db.execute(
        select(OperatorSession).where(OperatorSession.token_hash == token_hash).with_for_update()
    ).scalar_one()
