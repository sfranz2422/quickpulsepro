import uuid

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from polls.models import PollQuestion, PollResponse


class PermanentQuestionLinkTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("teach", password="pw12345!x")
        self.other_teacher = User.objects.create_user("other", password="pw12345!x")

        # An older question no longer showing in the room.
        self.retired = PollQuestion.objects.create(
            teacher=self.teacher, question_text="Retired question",
            option_a="Old A", option_b="Old B", is_active=False,
        )
        # The question currently showing in the room.
        self.current = PollQuestion.objects.create(
            teacher=self.teacher, question_text="Current question",
            option_a="New A", option_b="New B", is_active=True,
        )

    # ---------- the identifier itself ----------

    def test_every_question_gets_a_unique_public_id(self):
        ids = {q.public_id for q in PollQuestion.objects.all()}
        self.assertEqual(len(ids), 2)
        self.assertNotIn(None, ids)

    def test_unknown_public_id_is_404(self):
        resp = Client().get(reverse("poll_question_page", args=[uuid.uuid4()]))
        self.assertEqual(resp.status_code, 404)

    # ---------- the permanent page ----------

    def test_permanent_link_shows_an_inactive_question(self):
        resp = Client().get(
            reverse("poll_question_page", args=[self.retired.public_id]))
        self.assertContains(resp, "Retired question")
        self.assertNotContains(resp, "Current question")

    def test_room_still_shows_only_the_active_question(self):
        resp = Client().get(reverse("student_room", args=[self.teacher.id]))
        self.assertContains(resp, "Current question")
        self.assertNotContains(resp, "Retired question")

    def test_room_with_no_active_question(self):
        PollQuestion.objects.update(is_active=False)
        resp = Client().get(reverse("student_room", args=[self.teacher.id]))
        self.assertContains(resp, "No active question right now")

    # ---------- answering ----------

    def test_answer_via_permanent_link_is_recorded_against_that_question(self):
        """The regression that matters: an old link must not feed the live poll."""
        resp = Client().post(
            reverse("submit_poll_answer", args=[self.retired.public_id]),
            {"selected_option": "A"},
        )
        self.assertContains(resp, "Thank you")

        response = PollResponse.objects.get()
        self.assertEqual(response.question, self.retired)
        self.assertEqual(self.current.responses.count(), 0)

    def test_answer_via_room_is_recorded_against_the_active_question(self):
        Client().post(
            reverse("submit_response", args=[self.teacher.id]),
            {"selected_option": "B"},
        )
        response = PollResponse.objects.get()
        self.assertEqual(response.question, self.current)

    def test_short_answer_works_through_the_permanent_link(self):
        q = PollQuestion.objects.create(
            teacher=self.teacher, question_text="Takeaway?",
            question_type="SA", is_active=False,
        )
        student = Client()
        page = student.get(reverse("poll_question_page", args=[q.public_id]))
        self.assertContains(page, "<textarea")

        student.post(
            reverse("submit_poll_answer", args=[q.public_id]),
            {"text_answer": "  Recursion  "},
        )
        self.assertEqual(q.responses.get().text_answer, "Recursion")

    def test_blank_short_answer_through_permanent_link_is_rejected(self):
        q = PollQuestion.objects.create(
            teacher=self.teacher, question_text="Takeaway?",
            question_type="SA", is_active=False,
        )
        resp = Client().post(
            reverse("submit_poll_answer", args=[q.public_id]), {"text_answer": "  "})
        self.assertFalse(PollResponse.objects.exists())
        self.assertContains(resp, "This field is required")

    # ---------- the one-answer lock spans both entry points ----------

    def test_same_question_cannot_be_answered_from_both_entry_points(self):
        student = Client()
        student.post(reverse("submit_response", args=[self.teacher.id]),
                     {"selected_option": "A"})
        student.post(
            reverse("submit_poll_answer", args=[self.current.public_id]),
            {"selected_option": "B"}, follow=True)
        self.assertEqual(self.current.responses.count(), 1)

    def test_different_questions_can_both_be_answered_by_one_student(self):
        student = Client()
        student.post(reverse("submit_poll_answer", args=[self.retired.public_id]),
                     {"selected_option": "A"})
        student.post(reverse("submit_response", args=[self.teacher.id]),
                     {"selected_option": "B"})
        self.assertEqual(self.retired.responses.count(), 1)
        self.assertEqual(self.current.responses.count(), 1)

    # ---------- teacher-facing labels ----------

    def test_dashboard_shows_room_wording_and_permanent_links(self):
        self.client.force_login(self.teacher)
        html = self.client.get(reverse("dashboard")).content.decode()
        self.assertIn("Showing in Room", html)
        self.assertIn("Not in Room", html)
        self.assertIn("Remove from Room", html)
        self.assertIn("Show in Room", html)
        self.assertIn(str(self.current.public_id), html)
        self.assertIn(str(self.retired.public_id), html)
        self.assertNotIn("Make Active", html)

    def test_results_page_shows_the_permanent_link(self):
        self.client.force_login(self.teacher)
        html = self.client.get(
            reverse("question_results", args=[self.retired.id])).content.decode()
        self.assertIn(str(self.retired.public_id), html)
        self.assertIn("Not in Room", html)

    def test_toggling_room_visibility_still_allows_only_one(self):
        self.client.force_login(self.teacher)
        self.client.post(
            reverse("toggle_poll_question_active", args=[self.retired.id]))
        self.retired.refresh_from_db()
        self.current.refresh_from_db()
        self.assertTrue(self.retired.is_active)
        self.assertFalse(self.current.is_active)

    # ---------- access control ----------

    def test_delete_question_requires_login(self):
        resp = Client().get(reverse("delete_poll_question", args=[self.current.id]))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp["Location"])
        self.assertTrue(PollQuestion.objects.filter(id=self.current.id).exists())

    def test_teacher_cannot_delete_another_teachers_question(self):
        self.client.force_login(self.other_teacher)
        resp = self.client.get(
            reverse("delete_poll_question", args=[self.current.id]))
        self.assertEqual(resp.status_code, 404)
        self.assertTrue(PollQuestion.objects.filter(id=self.current.id).exists())
