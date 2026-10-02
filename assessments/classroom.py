"""Talking to Google Classroom on a teacher's behalf.

Tests only. Polls, quizzes and flash cards never touch Classroom.

A teacher connects once, through their own OAuth flow, separate from the
student sign-in button. Sign-in uses Google Identity Services and asks every
student for openid/email/profile; this asks one teacher for Classroom scopes,
with offline access so grades can be sent later without them present.
Folding the two together would put a Classroom consent screen in front of
every student.

Every call to Google goes through google_post, google_get or google_api, so
tests replace those three and never touch the network.
"""

import base64
import hashlib

import requests
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

from .models import ClassroomConnection


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
CLASSROOM_API = "https://classroom.googleapis.com/v1"

# Asked for all at once, so the teacher sees one consent screen rather than
# another each time a feature arrives. Posting a test and grading it needs
# coursework.students; matching a student to a Classroom one by email needs
# rosters and profile.emails. openid and email say WHICH account granted it.
SCOPES = [
    "openid",
    "email",
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.students",
    "https://www.googleapis.com/auth/classroom.rosters.readonly",
    "https://www.googleapis.com/auth/classroom.profile.emails",
]

# What Google's ?error= means, in words a teacher can act on.
AUTH_ERRORS = {
    "access_denied": (
        "You didn't allow QuickPulse Pro to use your Classroom, so nothing "
        "was connected."
    ),
    "admin_policy_enforced": (
        "Your school's Google admin doesn't allow this app to use Google "
        "Classroom. Ask your IT department to allow it."
    ),
}


def classroom_configured():
    return bool(
        settings.GOOGLE_OAUTH_CLIENT_ID and settings.GOOGLE_OAUTH_CLIENT_SECRET
    )


# ------------------------------------------------------------ the network


def _reply(response):
    try:
        return response.status_code, response.json()
    except ValueError:
        return response.status_code, {}


def google_post(url, data):
    """POST a form to Google. Returns (status, json). Never raises."""
    try:
        return _reply(requests.post(url, data=data, timeout=15))
    except requests.RequestException:
        return 0, {}


def google_get(url, access_token, params=None):
    """GET from a Google API as the teacher. Returns (status, json)."""
    try:
        return _reply(requests.get(
            url, params=params or {}, timeout=15,
            headers={"Authorization": "Bearer " + access_token}))
    except requests.RequestException:
        return 0, {}


def google_api(method, url, access_token, body=None, params=None):
    """Any other call to a Google API as the teacher. JSON in, (status, json)
    out. Never raises."""
    try:
        return _reply(requests.request(
            method, url, json=body, params=params or {}, timeout=20,
            headers={"Authorization": "Bearer " + access_token}))
    except requests.RequestException:
        return 0, {}


def google_message(data, fallback):
    """Google's own explanation from an error reply, for the teacher."""
    err = data.get("error") if isinstance(data, dict) else None

    if isinstance(err, dict) and err.get("message"):
        return err["message"]

    return fallback


def google_list(url, access_token, key, params=None):
    """Every page of a Classroom list. Returns (items, status), where status
    is that of the first page that failed, or 200. A dropped second page
    would mean students silently left ungraded."""
    items = []
    params = dict(params or {}, pageSize=100)

    for _ in range(50):
        status, data = google_get(url, access_token, params)

        if status != 200:
            return items, status

        items.extend(data.get(key, []))
        token = data.get("nextPageToken")

        if not token:
            break

        params["pageToken"] = token

    return items, 200


# ------------------------------------------------------------ tokens


def _token_box():
    digest = hashlib.sha256(
        ("classroom-token:" + settings.SECRET_KEY).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_token(token):
    return _token_box().encrypt(token.encode()).decode()


def decrypt_token(stored):
    return _token_box().decrypt(stored.encode()).decode()


def revoke(refresh_token):
    google_post(GOOGLE_REVOKE_URL, {"token": refresh_token})


def connection_for(user):
    return ClassroomConnection.objects.filter(teacher=user).first()


def access_token(user):
    """A fresh access token for this teacher, or (None, why).

    A connection Google no longer honours (revoked in their Google account,
    or by an admin), or one that can't be decrypted because SECRET_KEY
    changed, is DELETED, so the page goes back to offering Connect instead
    of failing the same way forever.
    """
    connection = connection_for(user)

    if connection is None:
        return None, "Connect your Google Classroom first."

    try:
        refresh = decrypt_token(connection.refresh_token)
    except InvalidToken:
        connection.delete()
        return None, "Your Classroom connection needs renewing. Connect it again."

    status, data = google_post(GOOGLE_TOKEN_URL, {
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
        "refresh_token": refresh,
        "grant_type": "refresh_token",
    })

    if status == 200 and data.get("access_token"):
        return data["access_token"], ""

    if data.get("error") == "invalid_grant":
        connection.delete()
        return None, (
            "Google no longer accepts QuickPulse Pro's connection to your "
            "Classroom. Connect it again."
        )

    return None, "Couldn't reach Google just now. Try again in a moment."


# ------------------------------------------------------------ classes


def teacher_courses(token):
    """The active classes this person teaches, as (courses, error)."""
    courses, status = google_list(
        CLASSROOM_API + "/courses", token, "courses",
        {"teacherId": "me", "courseStates": "ACTIVE"})

    if status != 200:
        return [], "Google wouldn't list your classes just now."

    return courses, ""
