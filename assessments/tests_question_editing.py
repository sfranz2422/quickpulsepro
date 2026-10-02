from django.test import Client
from django.urls import reverse

from assessments.models import TestAnswer, TestAttempt, TestQuestion
from assessments.tests_assessments import CLAIMS, AssessmentTestCase


class QuestionEditingTests(AssessmentTestCase):
    def edit_url(self, question):
        return reverse("edit_test_question", args=[question.id])

    def mc_data(self, **overrides):
        data = {
            "question_type": "MC",
            "prompt": "What keyword defines a function in Python?",
            "option_a": "func",
            "option_b": "def",
            "option_c": "",
            "option_d": "",
            "correct_option": "B",
            "points": 2,
        }
        data.update(overrides)
        return data

    def sa_data(self, **overrides):
        data = {
            "question_type": "SA",
            "prompt": "Explain what a loop does.",
            "points": 3,
        }
        data.update(overrides)
        return data

    def submit_for(self, sub, mc_choice, text):
        client = self.student_client(
            dict(CLAIMS, sub=sub, email=f"{sub}@school.org", name=sub))
        client.get(self.take_url())
        client.post(
            reverse("take_test_question", args=[self.test.public_id, 1]),
            {f"question_{self.mc.id}": mc_choice, "action": "next"})
        client.post(
            reverse("take_test_question", args=[self.test.public_id, 2]),
            {f"question_{self.sa.id}": text, "action": "next"})
        client.post(reverse("take_test_review", args=[self.test.public_id]))
        return TestAttempt.objects.get(student__google_sub=sub)

    def points_for(self, attempt, question):
        return attempt.answers.get(question=question).points_awarded

    # ------------------------------------------------------------ the page

    def test_the_workbench_links_to_each_questions_edit_page(self):
        resp = self.client.get(reverse("edit_test", args=[self.test.id]))
        self.assertContains(resp, self.edit_url(self.mc))
        self.assertContains(resp, self.edit_url(self.sa))

    def test_the_edit_page_is_prefilled(self):
        resp = self.client.get(self.edit_url(self.mc))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'value="func"')
        self.assertContains(resp, "What keyword defines a function")

    def test_the_edit_page_highlights_the_tests_section(self):
        resp = self.client.get(self.edit_url(self.mc))
        self.assertEqual(resp.context["active_section"], "tests")

    def test_the_edit_page_warns_when_students_have_answered(self):
        self.assertNotContains(
            self.client.get(self.edit_url(self.mc)), "already answered")
        self.submit_for("uid-ada", "B", "Repeats")
        self.assertContains(
            self.client.get(self.edit_url(self.mc)), "already answered")

    # ------------------------------------------------------------ saving

    def test_editing_a_question_saves_it(self):
        resp = self.client.post(self.edit_url(self.mc), self.mc_data(
            prompt="Which keyword starts a function?",
            option_c="lambda", correct_option="C", points=4))

        self.assertRedirects(resp, reverse("edit_test", args=[self.test.id]))
        self.mc.refresh_from_db()
        self.assertEqual(self.mc.prompt, "Which keyword starts a function?")
        self.assertEqual(self.mc.option_c, "lambda")
        self.assertEqual(self.mc.correct_option, "C")
        self.assertEqual(self.mc.points, 4)
        self.assertEqual(self.mc.order, 1)

    def test_editing_runs_the_same_validation_as_adding(self):
        resp = self.client.post(
            self.edit_url(self.mc), self.mc_data(correct_option="D"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Option D is blank")
        self.mc.refresh_from_db()
        self.assertEqual(self.mc.correct_option, "B")

    def test_type_can_change_before_anyone_answers(self):
        self.client.post(self.edit_url(self.mc), self.sa_data(points=2))
        self.mc.refresh_from_db()
        self.assertTrue(self.mc.is_short_answer)
        self.assertEqual(self.mc.option_a, "")
        self.assertEqual(self.mc.correct_option, "")

    def test_type_cannot_change_once_students_have_answered(self):
        self.submit_for("uid-ada", "B", "Repeats")

        resp = self.client.post(self.edit_url(self.mc), self.sa_data(points=2))

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "type can&#x27;t change")
        self.mc.refresh_from_db()
        self.assertEqual(self.mc.question_type, "MC")
        self.assertEqual(self.mc.option_b, "def")

    # ------------------------------------------------------------ re-scoring

    def test_changing_the_answer_key_rescores_submitted_answers(self):
        right = self.submit_for("uid-ada", "B", "Repeats")
        wrong = self.submit_for("uid-bob", "A", "Stuff")

        self.client.post(self.edit_url(self.mc), self.mc_data(correct_option="A"))

        self.assertEqual(self.points_for(right, self.mc), 0)
        self.assertEqual(self.points_for(wrong, self.mc), 2)

    def test_changing_points_rescores_correct_answers(self):
        attempt = self.submit_for("uid-ada", "B", "Repeats")
        self.client.post(self.edit_url(self.mc), self.mc_data(points=5))
        self.assertEqual(self.points_for(attempt, self.mc), 5)

    def test_rescoring_reports_how_many_scores_changed(self):
        self.submit_for("uid-ada", "B", "Repeats")
        self.submit_for("uid-bob", "A", "Stuff")

        resp = self.client.post(
            self.edit_url(self.mc), self.mc_data(points=5), follow=True)

        self.assertContains(resp, "1 student score updated")

    def test_a_blank_answer_stays_at_zero_after_rescoring(self):
        attempt = self.submit_for("uid-ada", "", "Repeats")
        self.client.post(self.edit_url(self.mc), self.mc_data(correct_option="A"))
        self.assertEqual(self.points_for(attempt, self.mc), 0)

    def test_a_wording_fix_leaves_hand_set_scores_alone(self):
        attempt = self.submit_for("uid-ada", "A", "Repeats")
        TestAnswer.objects.filter(
            attempt=attempt, question=self.mc).update(points_awarded=1)

        self.client.post(
            self.edit_url(self.mc), self.mc_data(prompt="Fixed a typo."))

        self.assertEqual(self.points_for(attempt, self.mc), 1)

    def test_in_progress_attempts_are_not_scored_early(self):
        client = self.student_client()
        client.get(self.take_url())
        client.post(
            reverse("take_test_question", args=[self.test.public_id, 1]),
            {f"question_{self.mc.id}": "A", "action": "next"})

        self.client.post(self.edit_url(self.mc), self.mc_data(correct_option="A"))

        answer = TestAnswer.objects.get(question=self.mc)
        self.assertIsNone(answer.points_awarded)

    def test_lowering_short_answer_points_caps_existing_grades(self):
        high = self.submit_for("uid-ada", "B", "Great answer")
        low = self.submit_for("uid-bob", "B", "Meh")
        ungraded = self.submit_for("uid-cy", "B", "Not graded yet")
        TestAnswer.objects.filter(attempt=high, question=self.sa).update(points_awarded=3)
        TestAnswer.objects.filter(attempt=low, question=self.sa).update(points_awarded=1)

        self.client.post(self.edit_url(self.sa), self.sa_data(points=2))

        self.assertEqual(self.points_for(high, self.sa), 2)
        self.assertEqual(self.points_for(low, self.sa), 1)
        self.assertIsNone(self.points_for(ungraded, self.sa))

    # ------------------------------------------------------------ access

    def test_another_teacher_cannot_edit_a_question(self):
        other = Client()
        other.force_login(self.other_teacher)

        self.assertEqual(other.get(self.edit_url(self.mc)).status_code, 404)
        resp = other.post(self.edit_url(self.mc), self.mc_data(prompt="Hijacked"))
        self.assertEqual(resp.status_code, 404)

        self.mc.refresh_from_db()
        self.assertNotEqual(self.mc.prompt, "Hijacked")

    def test_a_signed_in_student_cannot_edit_a_question(self):
        resp = self.student_client().get(self.edit_url(self.mc))
        self.assertIn("/login/", resp["Location"])
