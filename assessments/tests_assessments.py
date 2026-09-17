import csv
import io
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from assessments.markdown_utils import render_markdown
from assessments.models import Test, TestAnswer, TestAttempt, TestQuestion
from polls.models import Student


CLAIMS = {
    "iss": "https://accounts.google.com",
    "sub": "google-uid-ada",
    "email": "ada@school.org",
    "email_verified": True,
    "name": "Ada Lovelace",
}


@override_settings(GOOGLE_OAUTH_CLIENT_ID="test-client-id")
class AssessmentTestCase(TestCase):
    """Shared scaffolding: a teacher, a test, and a way to sign students in."""

    def setUp(self):
        self.teacher = User.objects.create_user("teach", password="pw12345!x")
        self.other_teacher = User.objects.create_user("other", password="pw12345!x")
        self.client.force_login(self.teacher)

        self.test = Test.objects.create(
            teacher=self.teacher, title="Unit 3 Test", is_open=True)

        self.mc = TestQuestion.objects.create(
            test=self.test, order=1, question_type="MC",
            prompt="What keyword defines a function in Python?",
            option_a="func", option_b="def", correct_option="B", points=2)

        self.sa = TestQuestion.objects.create(
            test=self.test, order=2, question_type="SA",
            prompt="Explain what a loop does.", points=3)

    def sign_in(self, client, claims=None):
        with patch("polls.views.verify_google_credential",
                   return_value=claims or CLAIMS):
            client.post(reverse("student_google_callback"),
                        {"credential": "token"})
        return client

    def student_client(self, claims=None):
        return self.sign_in(Client(), claims)

    def take_url(self):
        return reverse("take_test", args=[self.test.public_id])


class MarkdownRenderingTests(TestCase):
    def test_code_fence_becomes_a_highlightable_block(self):
        html = render_markdown("```python\nx = 1\n```")
        self.assertIn("<pre>", html)
        self.assertIn("language-python", html)

    def test_basic_formatting_survives(self):
        html = render_markdown("**bold** and `inline`")
        self.assertIn("<strong>bold</strong>", html)
        self.assertIn("<code>inline</code>", html)

    def test_script_tags_are_stripped(self):
        html = render_markdown("Hi <script>alert(1)</script>")
        self.assertNotIn("<script", html)
        self.assertNotIn("alert(1)", html)

    def test_event_handlers_are_stripped(self):
        html = render_markdown('<img src="x" onerror="alert(1)">')
        self.assertNotIn("onerror", html)

    def test_javascript_urls_are_stripped(self):
        html = render_markdown("[click](javascript:alert(1))")
        self.assertNotIn("javascript:", html)

    def test_empty_input(self):
        self.assertEqual(render_markdown(""), "")
        self.assertEqual(render_markdown(None), "")


class AuthoringTests(AssessmentTestCase):
    def test_create_test(self):
        resp = self.client.post(reverse("create_test"), {
            "title": "Quarter Exam", "instructions": "Answer **all** questions."})
        exam = Test.objects.get(title="Quarter Exam")
        self.assertEqual(exam.teacher, self.teacher)
        self.assertFalse(exam.is_open)
        self.assertRedirects(resp, reverse("edit_test", args=[exam.id]))

    def test_add_multiple_choice_question(self):
        self.client.post(reverse("add_test_question", args=[self.test.id]), {
            "question_type": "MC", "prompt": "2 + 2?",
            "option_a": "3", "option_b": "4", "option_c": "", "option_d": "",
            "correct_option": "B", "points": 1})
        question = self.test.questions.last()
        self.assertEqual(question.prompt, "2 + 2?")
        self.assertEqual(question.order, 3)

    def test_multiple_choice_requires_a_correct_option(self):
        resp = self.client.post(reverse("add_test_question", args=[self.test.id]), {
            "question_type": "MC", "prompt": "2 + 2?",
            "option_a": "3", "option_b": "4", "option_c": "", "option_d": "",
            "correct_option": "", "points": 1})
        self.assertContains(resp, "Choose which option is correct")
        self.assertEqual(self.test.questions.count(), 2)

    def test_correct_option_must_point_at_a_filled_option(self):
        resp = self.client.post(reverse("add_test_question", args=[self.test.id]), {
            "question_type": "MC", "prompt": "2 + 2?",
            "option_a": "3", "option_b": "4", "option_c": "", "option_d": "",
            "correct_option": "D", "points": 1})
        self.assertContains(resp, "Option D is blank")

    def test_short_answer_question_drops_options(self):
        self.client.post(reverse("add_test_question", args=[self.test.id]), {
            "question_type": "SA", "prompt": "Why?",
            "option_a": "leftover", "option_b": "junk", "option_c": "", "option_d": "",
            "correct_option": "A", "points": 5})
        question = self.test.questions.last()
        self.assertTrue(question.is_short_answer)
        self.assertEqual(question.option_a, "")
        self.assertEqual(question.correct_option, "")
        self.assertEqual(question.points, 5)

    def test_deleting_a_question_renumbers_the_rest(self):
        self.client.post(reverse("delete_test_question", args=[self.mc.id]))
        remaining = list(self.test.questions.all())
        self.assertEqual([q.order for q in remaining], [1])
        self.assertEqual(remaining[0], self.sa)

    def test_an_empty_prompt_is_caught_on_the_server(self):
        """The markdown editor hides the textarea, so `required` can't be relied
        on in the browser. The server has to be the one that says no."""
        resp = self.client.post(reverse("add_test_question", args=[self.test.id]), {
            "question_type": "MC", "prompt": "",
            "option_a": "3", "option_b": "4", "option_c": "", "option_d": "",
            "correct_option": "A", "points": 1})
        self.assertContains(resp, "This field is required")
        self.assertEqual(self.test.questions.count(), 2)

    def test_editor_script_drops_the_required_attribute(self):
        """A hidden field carrying `required` makes browsers silently refuse to
        submit the form, which is what broke the Add Question button."""
        html = self.client.get(
            reverse("edit_test", args=[self.test.id])).content.decode()
        self.assertIn('area.removeAttribute("required")', html)
        self.assertIn('typeof EasyMDE === "undefined"', html)

    def test_markdown_prompt_is_rendered_not_escaped_on_the_editor(self):
        self.mc.prompt = "```python\nprint(1)\n```"
        self.mc.save()
        html = self.client.get(reverse("edit_test", args=[self.test.id])).content.decode()
        self.assertIn("language-python", html)


class CSVImportTests(AssessmentTestCase):
    def upload(self, rows, header):
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)
        upload = io.BytesIO(buffer.getvalue().encode("utf-8"))
        upload.name = "questions.csv"
        return self.client.post(
            reverse("upload_test_csv", args=[self.test.id]), {"csv_file": upload})

    def test_test_format_imports(self):
        self.upload(
            [["MC", "Pick one", "a", "b", "", "", "A", "2"],
             ["SA", "Explain recursion", "", "", "", "", "", "4"]],
            ["question_type", "prompt", "option_a", "option_b",
             "option_c", "option_d", "correct_option", "points"])
        self.assertEqual(self.test.questions.count(), 4)
        added = list(self.test.questions.all())[2:]
        self.assertEqual(added[0].question_type, "MC")
        self.assertEqual(added[1].question_type, "SA")
        self.assertEqual(added[1].points, 4)

    def test_existing_quiz_csv_columns_are_accepted(self):
        """The quiz template's own headers import without being rewritten."""
        self.upload(
            [["What keyword defines a function in Python?",
              "func", "def", "function", "define", "B"]],
            ["question_text", "option_a", "option_b",
             "option_c", "option_d", "correctAnswer"])
        question = self.test.questions.last()
        self.assertEqual(question.question_type, "MC")
        self.assertEqual(question.correct_option, "B")
        self.assertEqual(question.points, 1)

    def test_rows_continue_the_existing_numbering(self):
        self.upload([["MC", "Pick", "a", "b", "", "", "A", "1"]],
                    ["question_type", "prompt", "option_a", "option_b",
                     "option_c", "option_d", "correct_option", "points"])
        self.assertEqual(self.test.questions.last().order, 3)

    def test_bad_correct_answer_is_rejected_and_nothing_imports(self):
        resp = self.upload([["MC", "Pick", "a", "b", "", "", "D", "1"]],
                           ["question_type", "prompt", "option_a", "option_b",
                            "option_c", "option_d", "correct_option", "points"])
        self.assertEqual(self.test.questions.count(), 2)
        messages = [str(m) for m in resp.wsgi_request._messages]
        self.assertIn("Valid answers for that row are: A, B", messages[0])

    def test_missing_prompt_column_is_rejected(self):
        resp = self.upload([["a", "b"]], ["option_a", "option_b"])
        self.assertEqual(self.test.questions.count(), 2)
        messages = [str(m) for m in resp.wsgi_request._messages]
        self.assertIn("needs a 'prompt' column", messages[0])

    def test_template_downloads(self):
        resp = self.client.get(reverse("download_test_csv_template"))
        self.assertEqual(resp["Content-Type"], "text/csv")
        self.assertIn("question_type", resp.content.decode())


class TakingTests(AssessmentTestCase):
    """Students see one question at a time, with back/forward and a review screen."""

    def q_url(self, number):
        return reverse("take_test_question", args=[self.test.public_id, number])

    def review_url(self):
        return reverse("take_test_review", args=[self.test.public_id])

    def answer(self, client, number, question, value, action="next"):
        return client.post(self.q_url(number), {
            f"question_{question.id}": value, "action": action})

    # ---------- getting in ----------

    def test_signing_in_is_required(self):
        resp = Client().get(self.take_url())
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("student_sign_in"), resp["Location"])

    def test_sign_in_returns_the_student_to_the_test(self):
        resp = Client().get(self.take_url())
        self.assertIn("next=", resp["Location"])
        self.assertIn(str(self.test.public_id), resp["Location"])

    def test_a_closed_test_cannot_be_started(self):
        self.test.is_open = False
        self.test.save()
        resp = self.student_client().get(self.take_url())
        self.assertContains(resp, "not open right now")
        self.assertFalse(TestAttempt.objects.exists())

    def test_a_test_with_no_questions_says_so(self):
        empty = Test.objects.create(teacher=self.teacher, title="Empty", is_open=True)
        resp = self.student_client().get(
            reverse("take_test", args=[empty.public_id]))
        self.assertContains(resp, "any questions yet")

    def test_the_entry_point_sends_them_to_the_first_question(self):
        client = self.student_client()
        resp = client.get(self.take_url())
        self.assertRedirects(resp, self.q_url(1))

    def test_opening_a_test_starts_an_attempt(self):
        self.student_client().get(self.take_url())
        attempt = TestAttempt.objects.get()
        self.assertEqual(attempt.student.email, "ada@school.org")
        self.assertFalse(attempt.is_submitted)

    # ---------- one question at a time ----------

    def test_only_one_question_is_on_the_page(self):
        client = self.student_client()
        client.get(self.take_url())
        html = client.get(self.q_url(1)).content.decode()
        self.assertIn("What keyword defines a function", html)
        self.assertNotIn("Explain what a loop does", html)
        self.assertIn("Question 1 of 2", html)

    def test_next_moves_forward_and_saves(self):
        client = self.student_client()
        client.get(self.take_url())
        resp = self.answer(client, 1, self.mc, "B")

        self.assertRedirects(resp, self.q_url(2))
        answer = TestAttempt.objects.get().answers.get(question=self.mc)
        self.assertEqual(answer.selected_option, "B")

    def test_back_moves_backward_and_saves(self):
        client = self.student_client()
        client.get(self.take_url())
        self.answer(client, 1, self.mc, "B")
        resp = self.answer(client, 2, self.sa, "A loop repeats.", action="prev")

        self.assertRedirects(resp, self.q_url(1))
        answer = TestAttempt.objects.get().answers.get(question=self.sa)
        self.assertEqual(answer.text_answer, "A loop repeats.")

    def test_an_earlier_answer_comes_back_prefilled(self):
        client = self.student_client()
        client.get(self.take_url())
        self.answer(client, 1, self.mc, "B")
        html = client.get(self.q_url(1)).content.decode()
        self.assertIn('value="B"\n                               checked', html.replace("\r", ""))

    def test_an_answer_can_be_changed_before_submitting(self):
        client = self.student_client()
        client.get(self.take_url())
        self.answer(client, 1, self.mc, "A")
        self.answer(client, 1, self.mc, "B")
        self.assertEqual(
            TestAttempt.objects.get().answers.get(question=self.mc).selected_option, "B")

    def test_the_last_question_leads_to_review(self):
        client = self.student_client()
        client.get(self.take_url())
        resp = self.answer(client, 2, self.sa, "It repeats work.")
        self.assertRedirects(resp, self.review_url())

    def test_review_can_be_reached_from_any_question(self):
        client = self.student_client()
        client.get(self.take_url())
        resp = self.answer(client, 1, self.mc, "B", action="review")
        self.assertRedirects(resp, self.review_url())

    def test_a_nonsense_question_number_goes_back_to_the_start(self):
        client = self.student_client()
        client.get(self.take_url())
        for number in (0, 99):
            resp = client.get(self.q_url(number))
            self.assertRedirects(resp, self.take_url(), target_status_code=302)

    def test_returning_later_resumes_at_the_first_blank_question(self):
        client = self.student_client()
        client.get(self.take_url())
        self.answer(client, 1, self.mc, "B")
        self.assertRedirects(client.get(self.take_url()), self.q_url(2))

    def test_returning_with_everything_answered_goes_to_review(self):
        client = self.student_client()
        client.get(self.take_url())
        self.answer(client, 1, self.mc, "B")
        self.answer(client, 2, self.sa, "It repeats.")
        self.assertRedirects(client.get(self.take_url()), self.review_url())

    # ---------- the review screen ----------

    def test_review_lists_every_question_with_its_state(self):
        client = self.student_client()
        client.get(self.take_url())
        self.answer(client, 1, self.mc, "B")

        resp = client.get(self.review_url())
        self.assertEqual(resp.context["unanswered"], [2])
        self.assertContains(resp, "Not answered")
        self.assertContains(resp, "Answered")

    def test_review_says_so_when_nothing_is_missing(self):
        client = self.student_client()
        client.get(self.take_url())
        self.answer(client, 1, self.mc, "B")
        self.answer(client, 2, self.sa, "It repeats.")

        resp = client.get(self.review_url())
        self.assertEqual(resp.context["unanswered"], [])
        self.assertContains(resp, "Every question has an answer")

    # ---------- submitting ----------

    def submit(self, client):
        return client.post(self.review_url())

    def test_submitting_auto_grades_multiple_choice_only(self):
        client = self.student_client()
        client.get(self.take_url())
        self.answer(client, 1, self.mc, "B")
        self.answer(client, 2, self.sa, "It repeats work.")
        self.submit(client)

        attempt = TestAttempt.objects.get()
        self.assertTrue(attempt.is_submitted)
        self.assertEqual(attempt.answers.get(question=self.mc).points_awarded, 2)
        self.assertIsNone(attempt.answers.get(question=self.sa).points_awarded)
        self.assertTrue(attempt.needs_grading)
        self.assertEqual(attempt.earned_points, 2)

    def test_a_wrong_choice_scores_zero(self):
        client = self.student_client()
        client.get(self.take_url())
        self.answer(client, 1, self.mc, "A")
        self.submit(client)
        self.assertEqual(
            TestAttempt.objects.get().answers.get(question=self.mc).points_awarded, 0)

    def test_skipped_questions_score_zero_rather_than_waiting_to_be_graded(self):
        client = self.student_client()
        client.get(self.take_url())
        self.submit(client)

        attempt = TestAttempt.objects.get()
        self.assertEqual(attempt.answers.count(), 2)
        self.assertEqual(attempt.answers.get(question=self.mc).points_awarded, 0)
        self.assertEqual(attempt.answers.get(question=self.sa).points_awarded, 0)
        self.assertFalse(attempt.needs_grading)

    def test_a_submitted_test_is_locked(self):
        client = self.student_client()
        client.get(self.take_url())
        self.answer(client, 1, self.mc, "B")
        self.submit(client)

        resp = client.get(self.take_url())
        self.assertContains(resp, "has been submitted")

        # Every student-facing route now refuses to change anything.
        self.answer(client, 1, self.mc, "A")
        self.submit(client)
        self.assertEqual(
            TestAttempt.objects.get().answers.get(question=self.mc).selected_option, "B")

    def test_two_students_get_separate_attempts(self):
        first = self.student_client()
        second = self.student_client(dict(CLAIMS, sub="uid-bob", email="bob@school.org",
                                          name="Bob"))
        first.get(self.take_url())
        second.get(self.take_url())
        self.assertEqual(TestAttempt.objects.count(), 2)
        self.assertEqual(Student.objects.count(), 2)

    def test_reopening_lets_a_student_resubmit(self):
        client = self.student_client()
        client.get(self.take_url())
        self.answer(client, 1, self.mc, "A")
        self.submit(client)

        attempt = TestAttempt.objects.get()
        self.client.post(reverse("reopen_attempt", args=[attempt.id]))

        attempt.refresh_from_db()
        self.assertFalse(attempt.is_submitted)
        self.assertEqual(attempt.reopened_count, 1)

        self.answer(client, 1, self.mc, "B")
        self.submit(client)
        attempt.refresh_from_db()
        self.assertTrue(attempt.is_submitted)
        self.assertEqual(attempt.answers.get(question=self.mc).points_awarded, 2)


class GradingAndReportingTests(AssessmentTestCase):
    def submit_for(self, name, sub, mc_choice, text):
        client = self.student_client(
            dict(CLAIMS, sub=sub, email=f"{sub}@school.org", name=name))
        client.get(self.take_url())
        client.post(
            reverse("take_test_question", args=[self.test.public_id, 1]),
            {f"question_{self.mc.id}": mc_choice, "action": "next"})
        client.post(
            reverse("take_test_question", args=[self.test.public_id, 2]),
            {f"question_{self.sa.id}": text, "action": "next"})
        client.post(reverse("take_test_review", args=[self.test.public_id]))
        return TestAttempt.objects.get(student__google_sub=sub)

    def test_results_lists_every_student(self):
        self.submit_for("Ada", "uid-ada", "B", "Repeats work")
        self.submit_for("Bob", "uid-bob", "A", "Does stuff")

        resp = self.client.get(reverse("test_results", args=[self.test.id]))
        self.assertContains(resp, "Ada")
        self.assertContains(resp, "Bob")
        self.assertEqual(resp.context["submitted_count"], 2)
        self.assertEqual(resp.context["total_points"], 5)

    def test_results_flags_questions_needing_grading(self):
        self.submit_for("Ada", "uid-ada", "B", "Repeats work")
        resp = self.client.get(reverse("test_results", args=[self.test.id]))
        self.assertEqual(list(resp.context["questions_needing_grading"]), [self.sa])

    def test_grading_a_short_answer_updates_the_score(self):
        attempt = self.submit_for("Ada", "uid-ada", "B", "Repeats work")
        answer = attempt.answers.get(question=self.sa)

        self.client.post(reverse("grade_test_question", args=[self.sa.id]),
                         {f"points_{answer.id}": "3"})

        answer.refresh_from_db()
        attempt.refresh_from_db()
        self.assertEqual(answer.points_awarded, 3)
        self.assertIsNotNone(answer.graded_at)
        self.assertEqual(attempt.earned_points, 5)
        self.assertFalse(attempt.needs_grading)
        self.assertEqual(attempt.status_label, "Graded")

    def test_points_are_clamped_to_the_question_maximum(self):
        attempt = self.submit_for("Ada", "uid-ada", "B", "Repeats work")
        answer = attempt.answers.get(question=self.sa)
        self.client.post(reverse("grade_test_question", args=[self.sa.id]),
                         {f"points_{answer.id}": "99"})
        answer.refresh_from_db()
        self.assertEqual(answer.points_awarded, 3)

    def test_blank_grade_boxes_leave_an_answer_ungraded(self):
        attempt = self.submit_for("Ada", "uid-ada", "B", "Repeats work")
        answer = attempt.answers.get(question=self.sa)
        self.client.post(reverse("grade_test_question", args=[self.sa.id]),
                         {f"points_{answer.id}": ""})
        answer.refresh_from_db()
        self.assertIsNone(answer.points_awarded)

    def test_attempt_detail_shows_each_answer(self):
        attempt = self.submit_for("Ada", "uid-ada", "B", "Loops repeat work")
        html = self.client.get(
            reverse("attempt_detail", args=[attempt.id])).content.decode()
        self.assertIn("Loops repeat work", html)
        self.assertIn("correct", html)

    def test_csv_export_has_a_row_per_student(self):
        self.submit_for("Ada", "uid-ada", "B", "Repeats work")
        self.submit_for("Bob", "uid-bob", "A", "Does stuff")

        resp = self.client.get(reverse("export_test_scores", args=[self.test.id]))
        rows = list(csv.reader(io.StringIO(resp.content.decode())))

        self.assertEqual(rows[0][:7],
                         ["student", "email", "status", "submitted_at",
                          "points", "possible", "percent"])
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0][7:], ["Q1", "Q2"])

    def test_student_text_is_escaped_in_the_grading_screen(self):
        attempt = self.submit_for("Ada", "uid-ada", "B", "<script>alert(1)</script>")
        html = self.client.get(
            reverse("grade_test_question", args=[self.sa.id])).content.decode()
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)


class AccessControlTests(AssessmentTestCase):
    def as_other_teacher(self):
        client = Client()
        client.force_login(self.other_teacher)
        return client

    def test_another_teacher_cannot_open_the_workbench(self):
        self.assertEqual(
            self.as_other_teacher().get(
                reverse("edit_test", args=[self.test.id])).status_code, 404)

    def test_another_teacher_cannot_see_results(self):
        self.assertEqual(
            self.as_other_teacher().get(
                reverse("test_results", args=[self.test.id])).status_code, 404)

    def test_another_teacher_cannot_grade(self):
        self.assertEqual(
            self.as_other_teacher().get(
                reverse("grade_test_question", args=[self.sa.id])).status_code, 404)

    def test_another_teacher_cannot_delete_a_question(self):
        self.as_other_teacher().post(
            reverse("delete_test_question", args=[self.mc.id]))
        self.assertTrue(TestQuestion.objects.filter(id=self.mc.id).exists())

    def test_anonymous_teacher_pages_redirect_to_login(self):
        for name, args in [
            ("edit_test", [self.test.id]),
            ("test_results", [self.test.id]),
            ("create_test", []),
        ]:
            resp = Client().get(reverse(name, args=args))
            self.assertIn("/login/", resp["Location"], name)

    def test_a_signed_in_student_cannot_reach_the_teacher_side(self):
        resp = self.student_client().get(reverse("test_results", args=[self.test.id]))
        self.assertIn("/login/", resp["Location"])

    def test_destructive_actions_reject_get(self):
        for name, args in [
            ("delete_test_question", [self.mc.id]),
            ("delete_test", [self.test.id]),
            ("toggle_test_open", [self.test.id]),
        ]:
            self.assertEqual(
                self.client.get(reverse(name, args=args)).status_code, 405, name)

    def test_a_test_cannot_be_opened_with_no_questions(self):
        empty = Test.objects.create(teacher=self.teacher, title="Empty")
        self.client.post(reverse("toggle_test_open", args=[empty.id]))
        empty.refresh_from_db()
        self.assertFalse(empty.is_open)
