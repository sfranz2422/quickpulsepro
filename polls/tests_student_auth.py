from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from polls.google_auth import GoogleAuthError, verify_google_credential
from polls.models import PollQuestion, PollResponse, Quiz, QuizQuestion, Student
from polls.students import STUDENT_SESSION_KEY


CLAIMS = {
    "iss": "https://accounts.google.com",
    "sub": "google-uid-123",
    "email": "ada@school.org",
    "email_verified": True,
    "name": "Ada Lovelace",
    "picture": "https://example.com/ada.jpg",
}


@override_settings(GOOGLE_OAUTH_CLIENT_ID="test-client-id.apps.googleusercontent.com")
class StudentSignInTests(TestCase):
    def sign_in(self, client=None, claims=None, next_url=""):
        client = client or Client()
        with patch("polls.views.verify_google_credential", return_value=claims or CLAIMS):
            return client.post(
                reverse("student_google_callback"),
                {"credential": "a-token", "next": next_url},
            )

    # ---------- the page ----------

    def test_sign_in_page_renders_the_google_button(self):
        html = Client().get(reverse("student_sign_in")).content.decode()
        self.assertIn("g_id_signin", html)
        self.assertIn("test-client-id.apps.googleusercontent.com", html)

    @override_settings(GOOGLE_OAUTH_CLIENT_ID="")
    def test_sign_in_page_says_so_when_unconfigured(self):
        html = Client().get(reverse("student_sign_in")).content.decode()
        self.assertIn("not set up on this site yet", html)
        self.assertNotIn("g_id_signin", html)

    # ---------- signing in ----------

    def test_valid_credential_creates_a_student_and_a_session(self):
        client = Client()
        resp = self.sign_in(client)

        student = Student.objects.get()
        self.assertEqual(student.google_sub, "google-uid-123")
        self.assertEqual(student.email, "ada@school.org")
        self.assertEqual(student.display_name, "Ada Lovelace")
        self.assertEqual(client.session[STUDENT_SESSION_KEY], student.id)
        self.assertEqual(resp.status_code, 302)

    def test_signing_in_again_updates_rather_than_duplicates(self):
        self.sign_in()
        renamed = dict(CLAIMS, name="Ada King", email="ada.king@school.org")
        self.sign_in(claims=renamed)

        student = Student.objects.get()
        self.assertEqual(Student.objects.count(), 1)
        self.assertEqual(student.full_name, "Ada King")
        self.assertEqual(student.email, "ada.king@school.org")

    def test_rejected_credential_signs_nobody_in(self):
        client = Client()
        with patch("polls.views.verify_google_credential",
                   side_effect=GoogleAuthError("Google could not verify that sign-in.")):
            resp = client.post(reverse("student_google_callback"), {"credential": "bad"})

        self.assertFalse(Student.objects.exists())
        self.assertNotIn(STUDENT_SESSION_KEY, client.session)
        self.assertRedirects(resp, reverse("student_sign_in"))

    def test_callback_rejects_get(self):
        self.assertEqual(
            Client().get(reverse("student_google_callback")).status_code, 405)

    def test_sign_in_returns_the_student_where_they_were(self):
        resp = self.sign_in(next_url="/student/1/")
        self.assertEqual(resp["Location"], "/student/1/")

    def test_offsite_next_is_ignored(self):
        resp = self.sign_in(next_url="https://evil.example.com/steal")
        self.assertEqual(resp["Location"], reverse("home"))

    def test_sign_out_clears_the_session(self):
        client = Client()
        self.sign_in(client)
        client.post(reverse("student_sign_out"))
        self.assertNotIn(STUDENT_SESSION_KEY, client.session)

    # ---------- attribution ----------

    def setUpQuestion(self):
        teacher = User.objects.create_user("teach", password="pw12345!x")
        question = PollQuestion.objects.create(
            teacher=teacher, question_text="Pick", option_a="Yes", option_b="No",
            is_active=True)
        return teacher, question

    def test_poll_answer_is_attributed_to_a_signed_in_student(self):
        teacher, question = self.setUpQuestion()
        client = Client()
        self.sign_in(client)
        client.post(reverse("submit_response", args=[teacher.id]),
                    {"selected_option": "A"})

        response = PollResponse.objects.get()
        self.assertEqual(response.student, Student.objects.get())

    def test_poll_answer_stays_anonymous_without_sign_in(self):
        teacher, question = self.setUpQuestion()
        Client().post(reverse("submit_response", args=[teacher.id]),
                      {"selected_option": "A"})
        self.assertIsNone(PollResponse.objects.get().student)

    def test_short_answer_is_attributed(self):
        teacher = User.objects.create_user("t2", password="pw12345!x")
        question = PollQuestion.objects.create(
            teacher=teacher, question_text="Takeaway?", question_type="SA",
            is_active=True)
        client = Client()
        self.sign_in(client)
        client.post(reverse("submit_poll_answer", args=[question.public_id]),
                    {"text_answer": "Recursion"})
        self.assertEqual(PollResponse.objects.get().student, Student.objects.get())

    def test_quiz_answer_is_attributed(self):
        teacher = User.objects.create_user("t3", password="pw12345!x")
        quiz = Quiz.objects.create(title="Q", teacher=teacher)
        QuizQuestion.objects.create(quiz=quiz, question_text="Q1", option_a="a",
                                    option_b="b", correctAnswer="A")
        client = Client()
        self.sign_in(client)
        client.get(reverse("start_quiz", args=[quiz.public_id]), follow=True)
        client.post(reverse("display_quiz", args=[quiz.public_id]),
                    {"selected_option": "A"})

        response = quiz.responses.get()
        self.assertEqual(response.student, Student.objects.get())
        self.assertTrue(response.is_correct)

    def test_quiz_progress_survives_signing_in_midway(self):
        """cycle_key() must not throw away an in-progress quiz."""
        teacher = User.objects.create_user("t4", password="pw12345!x")
        quiz = Quiz.objects.create(title="Q", teacher=teacher)
        for i in range(2):
            QuizQuestion.objects.create(quiz=quiz, question_text=f"Q{i}",
                                        option_a="a", option_b="b", correctAnswer="A")
        client = Client()
        client.get(reverse("start_quiz", args=[quiz.public_id]), follow=True)
        order_before = client.session[f"quiz_{quiz.id}_question_order"]

        self.sign_in(client)

        self.assertEqual(client.session[f"quiz_{quiz.id}_question_order"], order_before)

    # ---------- the two account systems stay apart ----------

    def test_teacher_nav_wins_when_both_are_signed_in(self):
        teacher = User.objects.create_user("teach", password="pw12345!x")
        client = Client()
        self.sign_in(client)
        client.force_login(teacher)

        html = client.get(reverse("dashboard")).content.decode()
        self.assertIn("Teacher Dashboard", html)
        self.assertNotIn("Student Sign In", html)

    def test_a_signed_in_student_gets_no_teacher_access(self):
        client = Client()
        self.sign_in(client)
        resp = client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp["Location"])

    @override_settings(GOOGLE_OAUTH_CLIENT_ID="")
    def test_nav_hides_sign_in_when_unconfigured(self):
        html = Client().get(reverse("home")).content.decode()
        self.assertNotIn("Student Sign In", html)

    def test_nav_offers_sign_in_when_configured(self):
        html = Client().get(reverse("home")).content.decode()
        self.assertIn("Student Sign In", html)


@override_settings(GOOGLE_OAUTH_CLIENT_ID="test-client-id.apps.googleusercontent.com")
class CredentialVerificationTests(TestCase):
    """Exercises the real verifier, with only Google's network call stubbed."""

    def verify(self, claims):
        with patch("polls.google_auth.id_token.verify_oauth2_token",
                   return_value=claims):
            return verify_google_credential("a-token")

    def test_good_claims_pass(self):
        self.assertEqual(self.verify(CLAIMS)["sub"], "google-uid-123")

    def test_unverified_email_is_rejected(self):
        with self.assertRaises(GoogleAuthError):
            self.verify(dict(CLAIMS, email_verified=False))

    def test_wrong_issuer_is_rejected(self):
        with self.assertRaises(GoogleAuthError):
            self.verify(dict(CLAIMS, iss="https://evil.example.com"))

    def test_missing_credential_is_rejected(self):
        with self.assertRaises(GoogleAuthError):
            verify_google_credential("")

    @override_settings(GOOGLE_OAUTH_CLIENT_ID="")
    def test_unconfigured_site_rejects_everything(self):
        with self.assertRaises(GoogleAuthError):
            verify_google_credential("a-token")

    @override_settings(GOOGLE_ALLOWED_DOMAINS="school.org")
    def test_allowlist_admits_a_matching_domain(self):
        self.assertEqual(self.verify(CLAIMS)["email"], "ada@school.org")

    @override_settings(GOOGLE_ALLOWED_DOMAINS="school.org")
    def test_allowlist_blocks_other_domains(self):
        with self.assertRaises(GoogleAuthError):
            self.verify(dict(CLAIMS, email="stranger@gmail.com", hd=None))

    def test_no_allowlist_admits_any_domain(self):
        self.assertEqual(
            self.verify(dict(CLAIMS, email="stranger@gmail.com"))["email"],
            "stranger@gmail.com",
        )
