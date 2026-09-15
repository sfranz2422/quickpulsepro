from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from polls.models import PollQuestion, PollResponse


class ClearResponsesTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("teach", password="pw12345!x")
        self.other = User.objects.create_user("other", password="pw12345!x")
        self.client.force_login(self.teacher)

        self.question = PollQuestion.objects.create(
            teacher=self.teacher, question_text="Pick one",
            option_a="Yes", option_b="No", is_active=True,
        )
        self.untouched = PollQuestion.objects.create(
            teacher=self.teacher, question_text="Other question",
            option_a="A", option_b="B", is_active=False,
        )
        for option in ("A", "A", "B"):
            PollResponse.objects.create(question=self.question, selected_option=option)
        PollResponse.objects.create(question=self.untouched, selected_option="A")

    def clear(self, question, client=None):
        client = client or self.client
        return client.post(reverse("clear_poll_responses", args=[question.id]))

    # ---------- clearing ----------

    def test_clearing_deletes_only_that_questions_responses(self):
        resp = self.clear(self.question)

        self.assertRedirects(resp, reverse("dashboard"))
        self.assertEqual(self.question.responses.count(), 0)
        self.assertEqual(self.untouched.responses.count(), 1)

    def test_clearing_reports_how_many_went(self):
        resp = self.clear(self.question, )
        messages = [str(m) for m in resp.wsgi_request._messages]
        self.assertIn("Cleared 3 responses", messages[0])

    def test_clearing_an_empty_question_is_harmless(self):
        self.question.responses.all().delete()
        resp = self.clear(self.question)
        self.assertRedirects(resp, reverse("dashboard"))
        self.assertEqual(self.question.responses.count(), 0)

    def test_the_question_itself_survives(self):
        public_id = self.question.public_id
        self.clear(self.question)
        self.question.refresh_from_db()
        self.assertEqual(self.question.public_id, public_id)
        self.assertTrue(self.question.is_active)

    # ---------- the re-answer reset ----------

    def test_round_one_keeps_the_legacy_session_key(self):
        self.assertEqual(self.question.answer_round, 1)
        self.assertEqual(
            self.question.answer_session_key(),
            f"answered_question_{self.question.id}",
        )

    def test_clearing_advances_the_round(self):
        self.clear(self.question)
        self.question.refresh_from_db()
        self.assertEqual(self.question.answer_round, 2)
        self.assertEqual(
            self.question.answer_session_key(),
            f"answered_question_{self.question.id}_round_2",
        )

    def test_a_student_who_answered_can_answer_again_after_a_clear(self):
        student = Client()
        student.post(reverse("submit_response", args=[self.teacher.id]),
                     {"selected_option": "A"})
        self.assertEqual(self.question.responses.count(), 4)

        # Locked out while the round stands.
        student.post(reverse("submit_response", args=[self.teacher.id]),
                     {"selected_option": "B"})
        self.assertEqual(self.question.responses.count(), 4)

        self.clear(self.question)

        # Same browser, same session, now allowed again.
        student.post(reverse("submit_response", args=[self.teacher.id]),
                     {"selected_option": "B"})
        self.assertEqual(self.question.responses.count(), 1)
        self.assertEqual(self.question.responses.get().selected_option, "B")

    def test_the_lock_still_holds_within_a_round(self):
        self.clear(self.question)
        student = Client()
        for option in ("A", "B"):
            student.post(reverse("submit_response", args=[self.teacher.id]),
                         {"selected_option": option})
        self.assertEqual(self.question.responses.count(), 1)

    def test_clearing_also_resets_the_permanent_link(self):
        student = Client()
        url = reverse("submit_poll_answer", args=[self.untouched.public_id])
        student.post(url, {"selected_option": "A"})
        self.assertEqual(self.untouched.responses.count(), 2)

        self.clear(self.untouched)
        student.post(url, {"selected_option": "B"})
        self.assertEqual(self.untouched.responses.count(), 1)

    # ---------- access control ----------

    def test_clearing_requires_login(self):
        resp = self.clear(self.question, client=Client())
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp["Location"])
        self.assertEqual(self.question.responses.count(), 3)

    def test_clearing_is_scoped_to_the_owning_teacher(self):
        intruder = Client()
        intruder.force_login(self.other)
        self.assertEqual(self.clear(self.question, client=intruder).status_code, 404)
        self.assertEqual(self.question.responses.count(), 3)

    def test_get_does_not_clear(self):
        self.client.get(reverse("clear_poll_responses", args=[self.question.id]))
        self.assertEqual(self.question.responses.count(), 3)
        self.question.refresh_from_db()
        self.assertEqual(self.question.answer_round, 1)

    # ---------- the dashboard button ----------

    def test_polling_page_shows_counts_and_an_enabled_button(self):
        html = self.client.get(reverse("polling_home")).content.decode()
        self.assertIn("Clear Responses", html)
        self.assertIn("Total responses: 3", html)
        self.assertIn(reverse("clear_poll_responses", args=[self.question.id]), html)

    def test_button_is_disabled_when_there_is_nothing_to_clear(self):
        PollResponse.objects.all().delete()
        html = self.client.get(reverse("polling_home")).content.decode()
        self.assertIn("disabled", html)
        self.assertIn("Total responses: 0", html)
