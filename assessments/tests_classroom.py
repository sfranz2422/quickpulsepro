from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.test import Client, override_settings
from django.urls import reverse

from assessments import classroom
from assessments.models import (
    ClassroomConnection, ClassroomPost, Test, TestAnswer, TestAttempt)
from assessments.tests_assessments import CLAIMS, AssessmentTestCase


ALL_SCOPES = " ".join(classroom.SCOPES)

COURSES = [
    {"id": "111", "name": "Period 2", "section": "Intro to Programming"},
    {"id": "222", "name": "Period 5"},
]


class FakeGoogle:
    """Stands in for google_post, google_get and google_api, recording calls."""

    def __init__(self, token_reply=None, courses=COURSES, work_reply=None):
        self.token_reply = token_reply or (200, {
            "access_token": "access-1",
            "refresh_token": "refresh-1",
            "scope": ALL_SCOPES,
        })
        self.courses = courses
        self.work_reply = work_reply or (200, {
            "id": "9001", "alternateLink": "https://classroom.google.com/c/x/a/9001"})
        self.posts, self.gets, self.api_calls = [], [], []

    def post(self, url, data):
        self.posts.append((url, data))

        if url == classroom.GOOGLE_REVOKE_URL:
            return 200, {}

        if data.get("grant_type") == "refresh_token":
            return 200, {"access_token": "access-2"}

        return self.token_reply

    def get(self, url, access_token, params=None):
        self.gets.append((url, params))

        if url == classroom.GOOGLE_USERINFO_URL:
            return 200, {"email": "teach@school.org"}

        if url.endswith("/courses"):
            return 200, {"courses": self.courses}

        return 404, {}

    def api(self, method, url, access_token, body=None, params=None):
        self.api_calls.append((method, url, body))
        return self.work_reply

    def __enter__(self):
        self._patches = [
            patch("assessments.classroom.google_post", self.post),
            patch("assessments.classroom.google_get", self.get),
            patch("assessments.classroom.google_api", self.api),
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in self._patches:
            p.stop()

    def revoked(self):
        return [data["token"] for url, data in self.posts
                if url == classroom.GOOGLE_REVOKE_URL]


@override_settings(
    GOOGLE_OAUTH_CLIENT_ID="test-client-id",
    GOOGLE_OAUTH_CLIENT_SECRET="test-secret",
)
class ClassroomTestCase(AssessmentTestCase):
    def page_url(self):
        return reverse("test_classroom", args=[self.test.id])

    def connect(self):
        ClassroomConnection.objects.create(
            teacher=self.teacher,
            refresh_token=classroom.encrypt_token("refresh-1"),
            google_email="teach@school.org")

    def start_connect(self):
        resp = self.client.get(
            reverse("classroom_connect") + f"?test={self.test.id}")
        return parse_qs(urlparse(resp["Location"]).query)

    def finish_connect(self, **params):
        state = self.client.session.get("classroom_oauth_state", "")
        query = {"state": state, "code": "abc", **params}
        return self.client.get(reverse("classroom_callback"), query)


@override_settings(GOOGLE_OAUTH_CLIENT_SECRET="")
class ClassroomSwitchedOffTests(AssessmentTestCase):
    def test_without_a_secret_the_page_does_not_exist(self):
        resp = self.client.get(reverse("test_classroom", args=[self.test.id]))
        self.assertEqual(resp.status_code, 404)

    def test_without_a_secret_the_workbench_has_no_classroom_button(self):
        resp = self.client.get(reverse("edit_test", args=[self.test.id]))
        self.assertNotContains(resp, reverse("test_classroom", args=[self.test.id]))


class ConnectingTests(ClassroomTestCase):
    def test_the_workbench_links_to_the_classroom_page(self):
        resp = self.client.get(reverse("edit_test", args=[self.test.id]))
        self.assertContains(resp, self.page_url())

    def test_the_page_highlights_the_tests_section(self):
        resp = self.client.get(self.page_url())
        self.assertEqual(resp.context["active_section"], "tests")

    def test_an_unconnected_teacher_is_offered_connect(self):
        resp = self.client.get(self.page_url())
        self.assertContains(resp, "Connect Google Classroom")

    def test_connect_sends_the_teacher_to_google_for_classroom_scopes(self):
        query = self.start_connect()

        self.assertEqual(query["client_id"], ["test-client-id"])
        self.assertEqual(query["access_type"], ["offline"])
        self.assertEqual(query["prompt"], ["select_account consent"])
        self.assertNotIn("login_hint", query)
        self.assertEqual(query["scope"], [ALL_SCOPES])
        self.assertEqual(
            query["state"], [self.client.session["classroom_oauth_state"]])
        self.assertTrue(query["redirect_uri"][0].endswith("/tests/classroom/callback/"))

    def test_a_successful_callback_stores_an_encrypted_token(self):
        self.start_connect()

        with FakeGoogle():
            resp = self.finish_connect()

        self.assertRedirects(resp, self.page_url(), fetch_redirect_response=False)
        connection = ClassroomConnection.objects.get(teacher=self.teacher)
        self.assertNotIn("refresh-1", connection.refresh_token)
        self.assertEqual(classroom.decrypt_token(connection.refresh_token), "refresh-1")
        self.assertEqual(connection.google_email, "teach@school.org")

    def test_a_callback_that_did_not_start_here_is_refused(self):
        with FakeGoogle():
            self.client.get(reverse("classroom_callback"),
                            {"state": "forged", "code": "abc"})

        self.assertFalse(ClassroomConnection.objects.exists())

    def test_declining_on_googles_screen_explains_itself(self):
        self.start_connect()
        state = self.client.session["classroom_oauth_state"]

        with FakeGoogle():
            resp = self.client.get(
                reverse("classroom_callback"),
                {"state": state, "error": "access_denied"}, follow=True)

        self.assertFalse(ClassroomConnection.objects.exists())
        self.assertContains(resp, "didn&#x27;t allow")

    def test_unticked_permissions_are_refused_and_given_back(self):
        self.start_connect()
        partial = (200, {
            "access_token": "access-1", "refresh_token": "refresh-1",
            "scope": "openid email " + classroom.SCOPES[2]})

        with FakeGoogle(token_reply=partial) as google:
            self.finish_connect()

        self.assertFalse(ClassroomConnection.objects.exists())
        self.assertEqual(google.revoked(), ["refresh-1"])

    def test_a_revoked_connection_is_forgotten(self):
        self.connect()

        google = FakeGoogle()
        google.post = lambda url, data: (400, {"error": "invalid_grant"})

        with google:
            resp = self.client.get(self.page_url())

        self.assertFalse(ClassroomConnection.objects.exists())
        self.assertContains(resp, "Connect Google Classroom")

    def test_disconnect_revokes_and_forgets(self):
        self.connect()

        with FakeGoogle() as google:
            self.client.post(reverse("classroom_disconnect"), {"test": self.test.id})

        self.assertFalse(ClassroomConnection.objects.exists())
        self.assertEqual(google.revoked(), ["refresh-1"])

    def test_disconnect_rejects_get(self):
        self.assertEqual(
            self.client.get(reverse("classroom_disconnect")).status_code, 405)


class PostingTests(ClassroomTestCase):
    def setUp(self):
        super().setUp()
        self.connect()

    def post_to(self, course="111", state="draft"):
        return self.client.post(
            reverse("post_test_to_classroom", args=[self.test.id]),
            {"course": course, "state": state}, follow=True)

    def test_the_page_lists_the_teachers_classes(self):
        with FakeGoogle():
            resp = self.client.get(self.page_url())

        self.assertContains(resp, "Period 2")
        self.assertContains(resp, "Period 5")
        self.assertContains(resp, "teach@school.org")

    def test_posting_creates_a_draft_classroom_assignment(self):
        with FakeGoogle() as google:
            resp = self.post_to()

        method, url, body = google.api_calls[0]
        self.assertEqual(method, "POST")
        self.assertTrue(url.endswith("/courses/111/courseWork"))
        self.assertEqual(body["title"], "Unit 3 Test")
        self.assertEqual(body["maxPoints"], 5)
        self.assertEqual(body["state"], "DRAFT")
        self.assertEqual(
            body["materials"][0]["link"]["url"],
            "https://testserver" + reverse("take_test", args=[self.test.public_id]))

        post = ClassroomPost.objects.get()
        self.assertEqual((post.course_id, post.course_name, post.work_id),
                         ("111", "Period 2", "9001"))
        self.assertContains(resp, "Saved as a draft in Period 2")

    def test_posting_can_assign_straight_away(self):
        with FakeGoogle() as google:
            self.post_to(state="publish")

        self.assertEqual(google.api_calls[0][2]["state"], "PUBLISHED")

    def test_a_test_can_go_to_several_classes(self):
        with FakeGoogle():
            self.post_to("111")
            self.post_to("222")

        self.assertEqual(ClassroomPost.objects.count(), 2)

    def test_a_posted_class_is_not_offered_again(self):
        with FakeGoogle():
            self.post_to("111")
            resp = self.client.get(self.page_url())

        self.assertEqual([c["id"] for c in resp.context["courses"]], ["222"])

    def test_posting_twice_to_one_class_is_refused(self):
        with FakeGoogle() as google:
            self.post_to("111")
            self.post_to("111")

        self.assertEqual(len(google.api_calls), 1)
        self.assertEqual(ClassroomPost.objects.count(), 1)

    def test_a_class_the_teacher_does_not_teach_is_refused(self):
        with FakeGoogle() as google:
            resp = self.post_to("999")

        self.assertEqual(google.api_calls, [])
        self.assertContains(resp, "isn&#x27;t one of yours")

    def test_a_test_with_no_points_cannot_be_posted(self):
        self.test.questions.all().delete()

        with FakeGoogle() as google:
            self.post_to()

        self.assertEqual(google.api_calls, [])
        self.assertFalse(ClassroomPost.objects.exists())

    def test_googles_refusal_is_shown(self):
        refusal = (403, {"error": {"message": "The caller does not have permission"}})

        with FakeGoogle(work_reply=refusal):
            resp = self.post_to()

        self.assertFalse(ClassroomPost.objects.exists())
        self.assertContains(resp, "The caller does not have permission")

    def test_posting_rejects_get(self):
        resp = self.client.get(
            reverse("post_test_to_classroom", args=[self.test.id]))
        self.assertEqual(resp.status_code, 405)


class ClassroomAccessTests(ClassroomTestCase):
    def test_another_teacher_cannot_see_or_post_this_test(self):
        other = Client()
        other.force_login(self.other_teacher)
        ClassroomConnection.objects.create(
            teacher=self.other_teacher,
            refresh_token=classroom.encrypt_token("theirs"))

        with FakeGoogle() as google:
            self.assertEqual(other.get(self.page_url()).status_code, 404)
            resp = other.post(
                reverse("post_test_to_classroom", args=[self.test.id]),
                {"course": "111"})

        self.assertEqual(resp.status_code, 404)
        self.assertEqual(google.api_calls, [])

    def test_a_signed_in_student_is_sent_to_the_teacher_login(self):
        resp = self.student_client().get(self.page_url())
        self.assertIn("/login/", resp["Location"])

    def test_a_tests_classroom_posts_go_when_it_is_deleted(self):
        ClassroomPost.objects.create(
            test=self.test, course_id="111", work_id="9001")
        Test.objects.filter(id=self.test.id).delete()
        self.assertFalse(ClassroomPost.objects.exists())


class PrivacyPageTests(AssessmentTestCase):
    def test_the_privacy_page_is_public(self):
        resp = Client().get("/privacy/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Privacy policy")
        self.assertContains(resp, "Limited Use")

    def test_the_connect_screen_links_to_it(self):
        with override_settings(GOOGLE_OAUTH_CLIENT_SECRET="test-secret"):
            resp = self.client.get(reverse("test_classroom", args=[self.test.id]))
        self.assertContains(resp, reverse("privacy"))


class GradebookGoogle(FakeGoogle):
    """A Classroom with classes, rosters and submissions to grade."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # work id -> courseWork reply; course id -> roster; work id -> subs
        self.works = {}
        self.rosters = {}
        self.submissions = {}
        self.refuse = set()

    def add_class(self, course_id, work_id, students, state="PUBLISHED",
                  max_points=5, unassigned=()):
        """students: {email: classroom user id}."""
        self.works[work_id] = {"id": work_id, "state": state, "maxPoints": max_points}
        self.rosters[course_id] = [
            {"userId": uid, "profile": {"emailAddress": email}}
            for email, uid in students.items()
        ]
        self.submissions[work_id] = [
            {"id": f"sub-{uid}", "userId": uid}
            for email, uid in students.items()
            if email not in unassigned and state != "DRAFT"
        ]

    def get(self, url, access_token, params=None):
        self.gets.append((url, params))
        parts = url.split("/")

        if url.endswith("/students"):
            return 200, {"students": self.rosters.get(parts[-2], [])}

        if url.endswith("/studentSubmissions"):
            return 200, {"studentSubmissions": self.submissions.get(parts[-2], [])}

        if "/courseWork/" in url:
            work = self.works.get(parts[-1])
            return (200, work) if work else (404, {})

        return super().get(url, access_token, params)

    def api(self, method, url, access_token, body=None, params=None):
        self.api_calls.append((method, url, body))

        if url.rsplit("/", 1)[-1] in self.refuse:
            return 403, {"error": {"message": "Not allowed"}}

        return 200, {}

    def grades(self):
        """{submission id: draft grade} for every grade sent."""
        return {
            url.rsplit("/", 1)[-1]: body["draftGrade"]
            for method, url, body in self.api_calls
            if body and "draftGrade" in body
        }


class SendingGradesTests(ClassroomTestCase):
    def setUp(self):
        super().setUp()
        self.connect()
        self.post = ClassroomPost.objects.create(
            test=self.test, course_id="111", course_name="Period 2",
            work_id="9001")

    def take(self, sub, email, choice="B", text="It repeats", grade=3):
        """A student submits; their short answer gets `grade` (None = ungraded)."""
        client = self.student_client(
            dict(CLAIMS, sub=sub, email=email, name=sub.title()))
        client.get(self.take_url())
        client.post(
            reverse("take_test_question", args=[self.test.public_id, 1]),
            {f"question_{self.mc.id}": choice, "action": "next"})
        client.post(
            reverse("take_test_question", args=[self.test.public_id, 2]),
            {f"question_{self.sa.id}": text, "action": "next"})
        client.post(reverse("take_test_review", args=[self.test.public_id]))

        attempt = TestAttempt.objects.get(student__google_sub=sub)

        if grade is not None:
            TestAnswer.objects.filter(
                attempt=attempt, question=self.sa).update(points_awarded=grade)

        return attempt

    def send(self, google):
        with google:
            return self.client.post(
                reverse("send_grades_to_classroom", args=[self.test.id]),
                follow=True)

    def test_a_finished_score_goes_as_a_draft_grade(self):
        self.take("ada", "Ada@School.org", choice="B", grade=2)
        google = GradebookGoogle()
        google.add_class("111", "9001", {"ada@school.org": "u1"})

        resp = self.send(google)

        self.assertEqual(google.grades(), {"sub-u1": 4})
        self.assertContains(resp, "Sent 1 grade to Google Classroom")

    def test_ungraded_short_answers_are_held_back_and_named(self):
        self.take("ada", "ada@school.org", grade=None)
        google = GradebookGoogle()
        google.add_class("111", "9001", {"ada@school.org": "u1"})

        resp = self.send(google)

        self.assertEqual(google.grades(), {})
        self.assertContains(resp, "short answers still to grade: Ada")

    def test_a_student_not_on_the_roster_is_named(self):
        self.take("ada", "ada@gmail.com")
        google = GradebookGoogle()
        google.add_class("111", "9001", {"ada@school.org": "u1"})

        resp = self.send(google)

        self.assertEqual(google.grades(), {})
        self.assertContains(resp, "Not on any of this test&#x27;s Classroom rosters")

    def test_a_student_not_given_the_assignment_is_named(self):
        self.take("ada", "ada@school.org")
        google = GradebookGoogle()
        google.add_class("111", "9001", {"ada@school.org": "u1"},
                         unassigned=["ada@school.org"])

        resp = self.send(google)

        self.assertEqual(google.grades(), {})
        self.assertContains(resp, "not given the assignment in Classroom: Ada")

    def test_each_student_goes_to_their_own_class(self):
        ClassroomPost.objects.create(
            test=self.test, course_id="222", course_name="Period 5",
            work_id="9002")
        self.take("ada", "ada@school.org", grade=3)
        self.take("bob", "bob@school.org", choice="A", grade=1)
        google = GradebookGoogle()
        google.add_class("111", "9001", {"ada@school.org": "u1"})
        google.add_class("222", "9002", {"bob@school.org": "u2"})

        self.send(google)

        self.assertEqual(google.grades(), {"sub-u1": 5, "sub-u2": 1})
        sent_urls = [url for _, url, body in google.api_calls if "draftGrade" in body]
        self.assertTrue(any("/courses/222/courseWork/9002/" in u for u in sent_urls))

    def test_a_draft_assignment_says_to_assign_it_first(self):
        self.take("ada", "ada@school.org")
        google = GradebookGoogle()
        google.add_class("111", "9001", {"ada@school.org": "u1"}, state="DRAFT")

        resp = self.send(google)

        self.assertEqual(google.grades(), {})
        self.assertContains(resp, "still a draft in Period 2")

    def test_changed_points_update_what_classroom_counts_it_out_of(self):
        google = GradebookGoogle()
        google.add_class("111", "9001", {}, max_points=3)

        self.send(google)

        method, url, body = google.api_calls[0]
        self.assertEqual((method, body), ("PATCH", {"maxPoints": 5}))
        self.assertTrue(url.endswith("/courseWork/9001"))

    def test_matching_points_are_left_alone(self):
        google = GradebookGoogle()
        google.add_class("111", "9001", {}, max_points=5)

        self.send(google)

        self.assertEqual(google.api_calls, [])

    def test_an_assignment_deleted_in_classroom_is_forgotten(self):
        google = GradebookGoogle()  # no work 9001: Google says 404

        resp = self.send(google)

        self.assertFalse(ClassroomPost.objects.exists())
        self.assertContains(resp, "deleted in Classroom for Period 2")

    def test_students_still_taking_it_are_not_sent(self):
        client = self.student_client()
        client.get(self.take_url())
        google = GradebookGoogle()
        google.add_class("111", "9001", {"ada@school.org": "u1"})

        resp = self.send(google)

        self.assertEqual(google.grades(), {})
        self.assertContains(resp, "1 student still taking the test")

    def test_a_refused_grade_is_named(self):
        self.take("ada", "ada@school.org")
        google = GradebookGoogle()
        google.add_class("111", "9001", {"ada@school.org": "u1"})
        google.refuse.add("sub-u1")

        resp = self.send(google)

        self.assertContains(resp, "Google refused: Ada (Not allowed)")

    def test_the_classroom_page_offers_sending_once_posted(self):
        google = GradebookGoogle()

        with google:
            resp = self.client.get(self.page_url())

        self.assertContains(
            resp, reverse("send_grades_to_classroom", args=[self.test.id]))

    def test_the_results_page_links_to_classroom(self):
        resp = self.client.get(reverse("test_results", args=[self.test.id]))
        self.assertContains(resp, self.page_url())

    def test_sending_rejects_get(self):
        resp = self.client.get(
            reverse("send_grades_to_classroom", args=[self.test.id]))
        self.assertEqual(resp.status_code, 405)

    def test_another_teacher_cannot_send_this_tests_grades(self):
        other = Client()
        other.force_login(self.other_teacher)
        google = GradebookGoogle()

        with google:
            resp = other.post(
                reverse("send_grades_to_classroom", args=[self.test.id]))

        self.assertEqual(resp.status_code, 404)
        self.assertEqual(google.api_calls, [])
