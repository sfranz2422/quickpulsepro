"""Verification of Google Sign-In credentials.

All of the token handling lives here so the views never touch token
internals, and so tests can substitute a fake verifier instead of talking
to Google over the network.
"""

from django.conf import settings

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token


# Google mints tokens under both spellings of the issuer.
GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


class GoogleAuthError(Exception):
    """Raised when a credential cannot be trusted."""


def google_sign_in_configured():
    """True once a Google client ID is present in the environment.

    Everything student-facing hides itself when this is False, so the app
    behaves exactly as before on a deployment that has not set it up.
    """
    return bool(getattr(settings, "GOOGLE_OAUTH_CLIENT_ID", ""))


def allowed_email_domains():
    raw = getattr(settings, "GOOGLE_ALLOWED_DOMAINS", "") or ""

    return [
        domain.strip().lower()
        for domain in raw.split(",")
        if domain.strip()
    ]


def verify_google_credential(credential):
    """Checks a Google ID token and returns its claims.

    Raises GoogleAuthError for anything that is not a valid, verified
    credential issued to this site.
    """
    if not google_sign_in_configured():
        raise GoogleAuthError("Student sign-in is not set up on this site.")

    if not credential:
        raise GoogleAuthError("No Google credential was supplied.")

    try:
        # Checks the signature, the audience (our client ID) and expiry.
        claims = id_token.verify_oauth2_token(
            credential,
            google_requests.Request(),
            settings.GOOGLE_OAUTH_CLIENT_ID,
        )
    except Exception as exc:
        raise GoogleAuthError("Google could not verify that sign-in.") from exc

    if claims.get("iss") not in GOOGLE_ISSUERS:
        raise GoogleAuthError("That sign-in did not come from Google.")

    if not claims.get("sub"):
        raise GoogleAuthError("That sign-in carried no account id.")

    if not claims.get("email_verified"):
        raise GoogleAuthError(
            "That Google account does not have a verified email address."
        )

    allowed = allowed_email_domains()

    if allowed:
        domain = (
            claims.get("hd")
            or claims.get("email", "").rsplit("@", 1)[-1]
        ).lower()

        if domain not in allowed:
            raise GoogleAuthError(
                "That account is not allowed to sign in to this site."
            )

    return claims
