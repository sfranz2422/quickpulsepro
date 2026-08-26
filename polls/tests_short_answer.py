from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from polls.models import PollQuestion, PollResponse


class ShortAnswerPollTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("teach", password="pw12345!x")
        self.client.force_login(self.teacher)

    # ---------- creating ----------

    def test_teacher_can_create_short_answer_question_without_options(self):
        resp = self.client.post(reverse("create_question"), {
            "question_type": "SA",
            "question_text": "What is one takeaway from today?",
            "option_a": "", "option_b": "", "option_c": "", "option_d": "",
        })
        self.assertEqual(resp.status_code, 302)

        q = PollQuestion.objects.get()
        self.assertEqual(q.question_type, "SA")
        self.assertTrue(q.is_short_answer)
        self.assertEqual(q.option_a, "")
        self.assertTrue(q.is_active)

    def test_short_answer_ignores_any_options_that_were_typed(self):
        self.client.post(reverse("create_question"), {
            "question_type": "SA",
            "question_text": "Q", "option_a": "leftover", "option_b": "junk",
            "option_c": "", "option_d": "",
        })
        q = PollQuestion.objects.get()
        self.assertEqual((q.option_a, q.option_b), ("", ""))

    def test_multiple_choice_still_requires_two_options(self):
        resp = self.client.post(reverse("create_question"), {
            "question_type": "MC",
            "question_text": "Pick one", "option_a": "Yes",
            "option_b": "", "option_c": "", "option_d": "",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(PollQuestion.objects.exists())
        self.assertContains(resp, "Option B is required")

    def test_multiple_choice_creates_normally(self):
        resp = self.client.post(reverse("create_question"), {
            "question_type": "MC",
            "question_text": "Pick one", "option_a": "Yes", "option_b": "No",
            "option_c": "", "option_d": "",
        })
        self.assertEqual(resp.status_code, 302)
        q = PollQuestion.objects.get()
        self.assertEqual(q.question_type, "MC")
        self.assertFalse(q.is_short_answer)

    def test_create_page_renders(self):
        resp = self.client.get(reverse("create_question"))
        self.assertContains(resp, 'name="question_type"')
        self.assertContains(resp, "multiple-choice-options")

    # ---------- answering ----------

    def _short_answer_question(self):
        return PollQuestion.objects.create(
            teacher=self.teacher, question_text="One takeaway?",
            question_type="SA", is_active=True,
        )

    def test_student_room_shows_textarea_for_short_answer(self):
        self._short_answer_question()
        resp = Client().get(reverse("student_room", args=[self.teacher.id]))
        self.assertContains(resp, "<textarea")
        self.assertNotContains(resp, 'type="radio"')

    def test_student_room_still_shows_radios_for_multiple_choice(self):
        PollQuestion.objects.create(
            teacher=self.teacher, question_text="Pick", question_type="MC",
            option_a="Yes", option_b="No", is_active=True,
        )
        resp = Client().get(reverse("student_room", args=[self.teacher.id]))
        self.assertContains(resp, 'type="radio"')
        self.assertNotContains(resp, "<textarea")

    def test_student_can_submit_a_short_answer(self):
        q = self._short_answer_question()
        student = Client()
        resp = student.post(
            reverse("submit_response", args=[self.teacher.id]),
            {"text_answer": "  Recursion clicked  "},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Thank you")

        r = PollResponse.objects.get()
        self.assertEqual(r.text_answer, "Recursion clicked")
        self.assertEqual(r.selected_option, "")
        self.assertEqual(r.question, q)

    def test_blank_short_answer_is_rejected(self):
        self._short_answer_question()
        student = Client()
        resp = student.post(
            reverse("submit_response", args=[self.teacher.id]),
            {"text_answer": "   "},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(PollResponse.objects.exists())
        self.assertContains(resp, "This field is required")

    def test_over_length_short_answer_is_rejected(self):
        self._short_answer_question()
        resp = Client().post(
            reverse("submit_response", args=[self.teacher.id]),
            {"text_answer": "x" * 501},
        )
        self.assertFalse(PollResponse.objects.exists())
        self.assertContains(resp, "at most 500 characters")

    def test_student_cannot_answer_the_same_question_twice(self):
        self._short_answer_question()
        student = Client()
        student.post(reverse("submit_response", args=[self.teacher.id]),
                     {"text_answer": "first"})
        student.post(reverse("submit_response", args=[self.teacher.id]),
                     {"text_answer": "second"})
        self.assertEqual(PollResponse.objects.count(), 1)

    # ---------- results ----------

    def test_results_group_matching_answers_ignoring_case_and_spacing(self):
        q = self._short_answer_question()
        for answer in ["Recursion", "recursion  ", " RECURSION", "Loops"]:
            PollResponse.objects.create(question=q, text_answer=answer)

        resp = self.client.get(reverse("question_results", args=[q.id]))
        rows = resp.context["results"]

        self.assertEqual(resp.context["total_responses"], 4)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["text"], "Recursion")
        self.assertEqual(rows[0]["count"], 3)
        self.assertEqual(rows[0]["percent"], 75)
        self.assertEqual(rows[0]["letter"], "")
        self.assertEqual(rows[1]["text"], "Loops")
        self.assertEqual(rows[1]["count"], 1)
        self.assertEqual(rows[1]["percent"], 25)

        self.assertContains(resp, "Recursion")
        self.assertContains(resp, "Short Answer")
        self.assertNotContains(resp, "No responses yet")

    def test_results_page_for_short_answer_with_no_responses(self):
        q = self._short_answer_question()
        resp = self.client.get(reverse("question_results", args=[q.id]))
        self.assertContains(resp, "No responses yet")

    def test_multiple_choice_results_unchanged(self):
        q = PollQuestion.objects.create(
            teacher=self.teacher, question_text="Pick", question_type="MC",
            option_a="Yes", option_b="No", is_active=True,
        )
        PollResponse.objects.create(question=q, selected_option="A")
        PollResponse.objects.create(question=q, selected_option="A")
        PollResponse.objects.create(question=q, selected_option="B")

        resp = self.client.get(reverse("question_results", args=[q.id]))
        rows = resp.context["results"]

        self.assertEqual([r["letter"] for r in rows], ["A", "B"])
        self.assertEqual([r["count"] for r in rows], [2, 1])
        self.assertEqual(rows[0]["percent"], 67)
        self.assertContains(resp, "A. Yes")

    def test_dashboard_lists_both_question_types(self):
        PollQuestion.objects.create(
            teacher=self.teacher, question_text="SA one", question_type="SA")
        PollQuestion.objects.create(
            teacher=self.teacher, question_text="MC one", question_type="MC",
            option_a="a", option_b="b")

        resp = self.client.get(reverse("dashboard"))
        self.assertContains(resp, "Short Answer")
        self.assertContains(resp, "Multiple Choice")
