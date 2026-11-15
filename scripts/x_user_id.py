"""Show an X account's numeric ID, for TEST_RECIPIENT_IDS.

Usage: python -m scripts.x_user_id <handle>
In live mode this makes one X profile read (about USD 0.01) with your connected account.
"""
import sys

from app.errors import DomainError, ProviderError
from app.services.seeds import parse_handles

NOT_FOUND = {"X_RESOURCE_UNAVAILABLE", "INVALID_HANDLE"}


def _runtime():
    from app.config import Settings
    from app.db import make_database
    from app.services.runtime import Runtime
    settings = Settings()
    _, factory = make_database(settings.database_url)
    return Runtime(factory, settings)


def main(argv=None, rt=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("Usage: python -m scripts.x_user_id <handle>")
        return 2
    try:
        handles = parse_handles(argv[0])
    except DomainError:
        handles = []
    if len(handles) != 1:
        print(f"'{argv[0]}' is not a single X handle, for example @someone.")
        return 1
    handle = handles[0]
    rt = rt or _runtime()
    try:
        profile = rt.read("user", handle)
    except DomainError as exc:
        print(f"Could not look up @{handle}: {exc.message}")
        if exc.code == "ACCOUNT_RECONNECT_REQUIRED":
            print("Open the app, go to Settings and click Connect with X first, then run this again.")
        return 1
    except ProviderError as exc:
        if exc.code in NOT_FOUND or exc.status == 404:
            print(f"X has no public account @{handle}.")
        else:
            print(f"X refused the lookup of @{handle} ({exc.code}).")
        return 1
    print(f"@{profile.get('username', handle)}  numeric ID: {profile['id']}")
    print(f"Add this line to .env:  TEST_RECIPIENT_IDS={profile['id']}")
    if rt.settings.app_mode == "fixture":
        print("(Synthetic mode: this is a made-up account. Switch to live mode to look up real accounts.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
