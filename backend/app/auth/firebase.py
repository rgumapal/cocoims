"""Firebase Auth integration — the one sign-in identity provider for this
app (email+password and Google both go through Firebase; SPEC §16 open
item #11). This app's own bcrypt/JWT login (app/auth/security.py) is left
in place but no longer used by the frontend — a deliberate, cheap-to-keep
fallback rather than a hard removal in the same pass that introduced this.

Verification is local signature checking against Google's public certs, not
a network call authenticated by this app's own credentials — the app is
only initialized with a fixed project ID so a token minted for some other
Firebase project can never be accepted here.
"""
import firebase_admin
from firebase_admin import auth as firebase_auth

from app.core.config import settings

_app: firebase_admin.App | None = None


def _get_app() -> firebase_admin.App:
    global _app
    if _app is None:
        _app = firebase_admin.initialize_app(options={"projectId": settings.firebase_project_id})
    return _app


def verify_firebase_id_token(id_token: str) -> dict:
    """Raises ValueError (invalid/expired token) or firebase_admin.exceptions.FirebaseError
    (network/cert-fetch failure) — both are caught by the caller and turned into a 401."""
    return firebase_auth.verify_id_token(id_token, app=_get_app())


def provision_firebase_credential(email: str, display_name: str) -> str:
    """Creates the Firebase Auth identity for a newly-created core.app_user
    (called from users.py's create_user) and returns a password-setup link
    for the admin to hand to that person.

    email_verified=True at creation, not left for a separate "click to
    verify" step: the email was just typed by an admin into the Users
    screen, which is already the trust boundary (same as Google's own
    pre-verified email) — Firebase's own verification flow exists for
    self-service sign-up, which this app deliberately doesn't have (SPEC/
    CLAUDE.md ACCESS: deny by default, accounts are admin-provisioned).

    No email is actually sent here — this backend has no email-delivery
    infrastructure (SMTP/SendGrid/etc.), and building one is out of scope
    for wiring up sign-in. The admin is expected to share the returned link
    through whatever channel they already use.
    """
    app = _get_app()
    try:
        firebase_auth.create_user(
            email=email, email_verified=True, display_name=display_name, app=app
        )
    except firebase_auth.EmailAlreadyExistsError:
        pass  # e.g. re-provisioning a reactivated user — reuse the existing identity
    return firebase_auth.generate_password_reset_link(email, app=app)
