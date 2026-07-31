"""DEV-ONLY: sets a known password on every seeded non-service user.

db/seed/002_client_data.sql seeds real Cocopan positions as placeholder
accounts with password_hash IS NULL — SSO-first, per SPEC §16 open item #11
(SSO provider unconfirmed). There is nothing to log in with locally until
something sets a password, so this script does that, idempotently, for
every account where is_service = FALSE. Service accounts (system@cocopan.ph,
svc.pos@cocopan.ph) are skipped on purpose: they authenticate via
core.api_key, not interactive login, and giving them a password would be
inventing a credential nothing in the spec asks for.

Never run this against anything but the local dev database. It hardcodes a
single shared password for every account, which is fine for exercising the
API locally and would be a serious problem anywhere real.

Usage (from backend/, with the venv active — run as a module, not a bare
script, so `app` resolves: a bare `python scripts/set_dev_passwords.py` only
puts scripts/ on sys.path, not backend/, and `import app` fails):
    python -m scripts.set_dev_passwords
"""
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.core.config import settings
from app.models import AppUser

DEV_PASSWORD = "cocopan-dev-2026"  # noqa: S105 — intentionally hardcoded, dev-only


def main() -> None:
    engine = create_engine(settings.database_url)  # owning role: this is an admin script
    with Session(engine) as session:
        users = session.execute(
            select(AppUser).where(AppUser.is_service.is_(False))
        ).scalars().all()

        if not users:
            print("No non-service users found — has db/seed/002_client_data.sql been applied?")
            return

        for user in users:
            user.password_hash = hash_password(DEV_PASSWORD)
        session.commit()

        print(f"Set the dev password on {len(users)} account(s):")
        for user in sorted(users, key=lambda u: u.email):
            print(f"  {user.email}")
        print(f"\nPassword for all of the above: {DEV_PASSWORD}")


if __name__ == "__main__":
    main()
