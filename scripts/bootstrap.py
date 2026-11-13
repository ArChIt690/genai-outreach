"""Create local configuration without printing or hardcoding credentials."""
import argparse
import getpass
import os
from pathlib import Path

from argon2 import PasswordHasher
from cryptography.fernet import Fernet


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-demo", action="store_true", help="Enable synthetic fixture sends only")
    parser.add_argument("--database-url", default="postgresql+psycopg://outreach:outreach@127.0.0.1:5432/outreach")
    parser.add_argument("--reset-password", action="store_true", help="Change only the operator password")
    args = parser.parse_args()
    destination = Path(".env")
    if destination.exists() and not args.reset_password:
        raise SystemExit(".env already exists. Edit it locally, or use --reset-password.")
    password = getpass.getpass("Choose operator password (at least 12 characters): ")
    if len(password) < 12:
        raise SystemExit("Use at least 12 characters.")
    if password != getpass.getpass("Confirm password: "):
        raise SystemExit("Passwords did not match.")
    encoded = PasswordHasher().hash(password)
    if args.reset_password:
        if not destination.exists():
            raise SystemExit("No .env exists. Run initial bootstrap first.")
        from dotenv import set_key
        set_key(destination, "OPERATOR_PASSWORD_HASH", encoded)
    else:
        template = Path(".env.example").read_text(encoding="utf-8")
        template = template.replace("OPERATOR_PASSWORD_HASH=", "OPERATOR_PASSWORD_HASH='" + encoded + "'")
        template = template.replace("TOKEN_ENCRYPTION_KEY=", "TOKEN_ENCRYPTION_KEY=" + Fernet.generate_key().decode())
        template = template.replace(
            "postgresql+psycopg://outreach:outreach@127.0.0.1:5432/outreach", args.database_url)
        if args.fixture_demo:
            template = template.replace("SEND_ENABLED=false", "SEND_ENABLED=true")
        fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(template)
    print("Local configuration saved. No secrets were printed. Start or restart the application.")


if __name__ == "__main__":
    main()
