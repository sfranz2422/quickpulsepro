"""Google Classroom pages for tests: connect, disconnect, post a test.

See classroom.py for how the connection works and why it is separate from
student sign-in.
"""

import re
import secrets
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from . import classroom
from .models import ClassroomConnection, ClassroomPost, Test


STATE_KEY = "classroom_oauth_state"
RETURN_KEY = "classroom_return_test"


def _require_configured():
    if not classroom.classroom_configured():
        raise Http404


def _absolute(request, path):
    url = request.build_absolute_uri(path)

    # Render terminates TLS before Django, so requests arrive looking like
    # http. Google compares the redirect URI exactly, scheme included.
    if not settings.DEBUG and url.startswith("http://"):
        url = "https://" + url[len("http://"):]

    return url


def _callback_url(request):
    return _absolute(request, reverse("classroom_callback"))


def _back_to(request, test_id=None):
    if test_id:
        return redirect("test_classroom", test_id=test_id)

    return redirect("tests_home")


def _return_test_id(request):
    """The test whose Classroom page started this, if it is still theirs."""
    test_id = request.session.pop(RETURN_KEY, None)

    if test_id and Test.objects.filter(id=test_id, teacher=request.user).exists():
        return test_id

    return None


@login_required
def test_classroom(request, test_id):
    _require_configured()
    test = get_object_or_404(Test, id=test_id, teacher=request.user)

    connection = classroom.connection_for(request.user)
    posts = list(test.classroom_posts.all())
    courses, error = [], ""

    if connection is not None:
        token, error = classroom.access_token(request.user)

        if token:
            courses, error = classroom.teacher_courses(token)
        else:
            # access_token() may have just forgotten a dead connection.
            connection = classroom.connection_for(request.user)

    posted_ids = {post.course_id for post in posts}

    return render(request, "assessments/test_classroom.html", {
        "test": test,
        "connection": connection,
        "posts": posts,
        "courses": [c for c in courses if c.get("id") not in posted_ids],
        "classroom_error": error,
    })


@login_required
def classroom_connect(request):
    _require_configured()

    test_id = request.GET.get("test", "")
    request.session[RETURN_KEY] = int(test_id) if test_id.isdigit() else None

    # Ties Google's reply to this browser's request. Without it, a crafted
    # link could finish a connect flow in a teacher's session with someone
    # else's Google account.
    state = secrets.token_urlsafe(24)
    request.session[STATE_KEY] = state

    params = {
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "redirect_uri": _callback_url(request),
        "response_type": "code",
        "scope": " ".join(classroom.SCOPES),
        # offline: a refresh token, so grades can be sent later.
        # select_account: always show the account chooser, so a teacher
        # signed in to several Google accounts picks the school one rather
        # than getting whichever the browser used last. consent: Google only
        # hands out a refresh token on a consent screen, and a reconnect
        # without one would store nothing. No login_hint: teacher emails
        # here needn't be Google accounts, and a hint skips the chooser.
        "access_type": "offline",
        "prompt": "select_account consent",
        "include_granted_scopes": "true",
        "state": state,
    }

    return redirect(classroom.GOOGLE_AUTH_URL + "?" + urlencode(params))


@login_required
def classroom_callback(request):
    _require_configured()

    expected = request.session.pop(STATE_KEY, None)
    test_id = _return_test_id(request)

    def fail(reason):
        messages.error(request, reason)
        return _back_to(request, test_id)

    if not expected or request.GET.get("state") != expected:
        return fail(
            "That Classroom connection didn't start from this site. "
            "Try Connect again."
        )

    error = request.GET.get("error")

    if error:
        return fail(classroom.AUTH_ERRORS.get(
            error, f"Google didn't connect your Classroom ({error})."))

    status, data = classroom.google_post(classroom.GOOGLE_TOKEN_URL, {
        "code": request.GET.get("code", ""),
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
        "redirect_uri": _callback_url(request),
        "grant_type": "authorization_code",
    })

    access, refresh = data.get("access_token"), data.get("refresh_token")

    if status != 200 or not access or not refresh:
        return fail("Google didn't finish connecting your Classroom. Try again.")

    # The consent screen has a tick box per permission, and a teacher can
    # untick some. A half-granted token would fail later, when grades are
    # sent, with an error nobody could trace back to this screen.
    granted = set((data.get("scope") or "").split())
    missing = [
        scope for scope in classroom.SCOPES
        if scope.startswith("https://") and scope not in granted
    ]

    if missing:
        classroom.revoke(refresh)
        return fail(
            "QuickPulse Pro needs every Classroom permission on that screen "
            "to post tests and send grades. Connect again and leave all the "
            "boxes ticked."
        )

    status, info = classroom.google_get(classroom.GOOGLE_USERINFO_URL, access)
    google_email = (info.get("email") or "").strip() if status == 200 else ""

    ClassroomConnection.objects.update_or_create(
        teacher=request.user,
        defaults={
            "refresh_token": classroom.encrypt_token(refresh),
            "google_email": google_email,
        },
    )

    messages.success(
        request,
        f"Google Classroom connected{' as ' + google_email if google_email else ''}."
    )
    return _back_to(request, test_id)


@login_required
@require_POST
def classroom_disconnect(request):
    _require_configured()

    connection = classroom.connection_for(request.user)

    if connection is not None:
        # Revoked at Google as well as forgotten here, so disconnecting
        # really withdraws the permission rather than just hiding it.
        try:
            classroom.revoke(classroom.decrypt_token(connection.refresh_token))
        except Exception:
            pass

        connection.delete()
        messages.success(request, "Google Classroom disconnected.")

    test_id = request.POST.get("test", "")
    owned = (
        test_id.isdigit()
        and Test.objects.filter(id=test_id, teacher=request.user).exists()
    )
    return _back_to(request, int(test_id) if owned else None)


@login_required
@require_POST
def post_test_to_classroom(request, test_id):
    """Create this test as an assignment in one of the teacher's classes.

    Google only lets an app grade coursework the app created, so this is
    what makes sending grades possible later. Once per class: posting twice
    to the same class would show students two of everything.
    """
    _require_configured()
    test = get_object_or_404(Test, id=test_id, teacher=request.user)

    def fail(reason):
        messages.error(request, reason)
        return redirect("test_classroom", test_id=test.id)

    course_id = request.POST.get("course", "")

    if not re.fullmatch(r"[0-9]{1,30}", course_id):
        return fail("Choose a class.")

    total = test.total_points

    if not total:
        return fail("Add some questions first. Classroom only takes grades on "
                    "work with points.")

    if test.classroom_posts.filter(course_id=course_id).exists():
        return fail("This test is already posted to that class.")

    token, why = classroom.access_token(request.user)

    if token is None:
        return fail(why)

    # Asked of Google rather than trusted from the form: the class's name,
    # and proof that this teacher teaches it.
    courses, error = classroom.teacher_courses(token)

    if error:
        return fail(error)

    course = next((c for c in courses if c.get("id") == course_id), None)

    if course is None:
        return fail("That class isn't one of yours in Google Classroom.")

    draft = request.POST.get("state") == "draft"

    status, work = classroom.google_api(
        "POST",
        f"{classroom.CLASSROOM_API}/courses/{course_id}/courseWork",
        token,
        body={
            "title": test.title,
            "description": (
                "Open the test from the link and sign in with your school "
                "Google account."
            ),
            "materials": [{"link": {
                "url": _absolute(request, reverse("take_test", args=[test.public_id])),
            }}],
            "workType": "ASSIGNMENT",
            "state": "DRAFT" if draft else "PUBLISHED",
            "maxPoints": total,
        },
    )

    if status != 200 or not work.get("id"):
        return fail(classroom.google_message(
            work, "Google wouldn't create the assignment."))

    post = ClassroomPost.objects.create(
        test=test,
        course_id=course_id,
        course_name=(course.get("name") or "")[:200],
        work_id=str(work["id"])[:32],
        url=(work.get("alternateLink") or "")[:500],
    )

    if draft:
        messages.success(
            request,
            f"Saved as a draft in {post.course_name}. Assign it from "
            "Classroom when you're ready."
        )
    else:
        messages.success(request, f"Posted to {post.course_name}.")

    return redirect("test_classroom", test_id=test.id)


def _names(people):
    return ", ".join(sorted(people, key=str.lower))


@login_required
@require_POST
def send_grades_to_classroom(request, test_id):
    """Send every finished score to Classroom as a DRAFT grade, each to the
    class the student is in.

    Draft, not assigned: the teacher sees them in Classroom before students
    do, and returns them there. A student is matched to Classroom by their
    school email, which is why signing in with the school account matters.
    Anyone who can't be sent is named in the reply, not skipped in silence.
    Pressing it again simply sends the current scores again.
    """
    _require_configured()
    test = get_object_or_404(Test, id=test_id, teacher=request.user)

    def back():
        return redirect("test_classroom", test_id=test.id)

    if not test.classroom_posts.exists():
        messages.error(request, "Post this test to a class first.")
        return back()

    token, why = classroom.access_token(request.user)

    if token is None:
        messages.error(request, why)
        return back()

    classes, gone, error = classroom.class_lists(test, token)

    if gone:
        messages.warning(
            request,
            f"This test's assignment was deleted in Classroom for "
            f"{_names(gone)}, so it's no longer linked there. Post it again "
            "to send grades to that class."
        )

    if error:
        messages.error(request, error)
        return back()

    if not classes:
        return back()

    total = test.total_points
    drafts = []

    for entry in classes:
        work = entry["work"]
        name = entry["post"].course_name or "a class"

        if work.get("state") == "DRAFT":
            drafts.append(name)

        # Questions edited since posting change what the test is out of.
        if work.get("maxPoints") != total:
            status, data = classroom.google_api(
                "PATCH",
                f"{classroom.CLASSROOM_API}/courses/{entry['post'].course_id}"
                f"/courseWork/{entry['post'].work_id}",
                token,
                body={"maxPoints": total},
                params={"updateMask": "maxPoints"},
            )

            if status != 200:
                messages.warning(request, (
                    f"Couldn't update {name} to be out of {total} points: "
                    + classroom.google_message(data, "Google refused.")
                ))

    attempts = (
        test.attempts
        .select_related("student")
        .prefetch_related("answers")
    )

    to_send, waiting, unmatched, unassigned = [], [], [], []
    in_progress = 0

    for attempt in attempts:
        student = attempt.student

        if not attempt.is_submitted:
            in_progress += 1
            continue

        if attempt.needs_grading:
            waiting.append(student.display_name)
            continue

        email = student.email.strip().lower()
        target, on_a_roster = None, False

        for entry in classes:
            if email in entry["emails"]:
                on_a_roster = True
                submission_id = entry["emails"][email]

                if submission_id:
                    target = (entry["post"], submission_id)
                    break

        if target:
            to_send.append((student, attempt.earned_points, *target))
        elif on_a_roster:
            unassigned.append(student.display_name)
        else:
            unmatched.append(student.display_name)

    def send(item):
        student, score, post, submission_id = item
        status, data = classroom.google_api(
            "PATCH",
            f"{classroom.CLASSROOM_API}/courses/{post.course_id}"
            f"/courseWork/{post.work_id}/studentSubmissions/{submission_id}",
            token,
            body={"draftGrade": score},
            params={"updateMask": "draftGrade"},
        )

        if status == 200:
            return None

        return f"{student.display_name} ({classroom.google_message(data, 'refused')})"

    # One call per student. Several at once, so a few full classes finish
    # well inside the server's request timeout.
    with ThreadPoolExecutor(max_workers=8) as pool:
        failed = [result for result in pool.map(send, to_send) if result]

    sent = len(to_send) - len(failed)

    if sent:
        messages.success(
            request,
            f"Sent {sent} grade{'s' if sent != 1 else ''} to Google Classroom "
            "as drafts. Return them in Classroom when you're ready."
        )
    elif not (waiting or unmatched or unassigned or failed or drafts):
        messages.info(request, "No submitted tests to send yet.")

    if drafts:
        messages.warning(request, (
            f"The assignment is still a draft in {_names(drafts)}. Assign it "
            "in Classroom, then send grades again."
        ))

    if waiting:
        messages.warning(request, (
            f"Not sent yet, short answers still to grade: {_names(waiting)}."
        ))

    if unassigned:
        messages.warning(request, (
            "In your class but not given the assignment in Classroom: "
            f"{_names(unassigned)}."
        ))

    if unmatched:
        messages.warning(request, (
            "Not on any of this test's Classroom rosters (check they signed "
            f"in with their school account): {_names(unmatched)}."
        ))

    if failed:
        messages.error(request, f"Google refused: {_names(failed)}.")

    if in_progress:
        messages.info(request, (
            f"{in_progress} student{'s' if in_progress != 1 else ''} still "
            "taking the test, not sent."
        ))

    return back()
