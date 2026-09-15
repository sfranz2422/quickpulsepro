"""Student sessions.

Students are not django.contrib.auth users, so they get their own small
session helpers. Keeping the two apart means a student signing in can
never reach the teacher side of the app.
"""

from django.shortcuts import resolve_url
from django.utils.http import url_has_allowed_host_and_scheme

from .models import Student


STUDENT_SESSION_KEY = "student_id"


def get_current_student(request):
    """The signed-in student for this browser, or None."""
    student_id = request.session.get(STUDENT_SESSION_KEY)

    if not student_id:
        return None

    student = Student.objects.filter(id=student_id).first()

    if student is None:
        # The record was deleted out from under the session.
        request.session.pop(STUDENT_SESSION_KEY, None)

    return student


def sign_in_student(request, student):
    # A fresh session id on sign-in, so a stolen pre-login session key is
    # useless afterwards.
    request.session.cycle_key()
    request.session[STUDENT_SESSION_KEY] = student.id


def sign_out_student(request):
    request.session.pop(STUDENT_SESSION_KEY, None)


def safe_next_url(request, default="home"):
    """Where to send a student after signing in or out.

    Only same-site destinations are honoured; anything else falls back to
    the default so the sign-in page can't be used as an open redirect.
    """
    candidate = request.POST.get("next") or request.GET.get("next")

    if candidate and url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate

    return resolve_url(default)
