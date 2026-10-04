from django.urls import reverse

from assessments.markdown_utils import render_markdown_with_blanks
from assessments.models import TestAnswer, TestAttempt, TestQuestion
from assessments.tests_assessments import CLAIMS, AssessmentTestCase


class NewQuestionTypeTestCase(AssessmentTestCase):
    """The base test plus one fill in the blank and one matching question."""

    def setUp(self):
        super().setUp()

        self.fb = TestQuestion.objects.create(
            test=self.test, order=3, question_type="FB",
            prompt="A function is defined with ___ and sends a value back with ___.",
            blank_answers=[["def"], ["return", "return None"]],
            points=2)

        self.mt = TestQuestion.objects.create(
            test=self.test, order=4, question_type="MT",
            prompt="Match each type to an example.",
            match_pairs=[["int", "42"], ["str", "'hi'"], ["bool", "True"],
                         ["float", "3.5"]],
            match_extras=["None"],
            points=4)

    def add_url(self):
        return reverse("add_test_question", args=[self.test.id])

    def question_url(self, number):
        return reverse("take_test_question", args=[self.test.public_id, number])

    def fb_data(self, **overrides):
        data = {
            "question_type": "FB",
            "prompt": "Python loops with ___ and ___.",
            "blank_answers_text": "for\nwhile",
            "points": 2,
        }
        data.update(overrides)
        return data

    def mt_data(self, pairs, **overrides):
        data = {"question_type": "MT", "prompt": "Match them.", "points": 2}

        for index, (left, right) in enumerate(pairs):
            data[f"match_left_{index}"] = left
            data[f"match_right_{index}"] = right

        data.update(overrides)
        return data

    def answer_and_submit(self, client, fb=None, mt=None):
        """Answers the FB and MT questions (pages 3 and 4), then submits."""
        client.get(self.take_url())

        if fb is not None:
            client.post(self.question_url(3), {
                **{f"question_{self.fb.id}_{n}": value
                   for n, value in enumerate(fb, start=1)},
                "action": "next",
            })

        if mt is not None:
            client.post(self.question_url(4), {
                **{f"question_{self.mt.id}_{n}": value
                   for n, value in enumerate(mt, start=1)},
                "action": "next",
            })

        client.post(reverse("take_test_review", args=[self.test.public_id]))

    def answer_for(self, question, sub=CLAIMS["sub"]):
        return TestAnswer.objects.get(
            question=question, attempt__student__google_sub=sub)


class AuthoringTests(NewQuestionTypeTestCase):
    def test_adding_a_fill_in_the_blank_question(self):
        resp = self.client.post(self.add_url(), self.fb_data(
            blank_answers_text="for | for loop\n  while  "))

        self.assertRedirects(resp, reverse("edit_test", args=[self.test.id]))
        question = self.test.questions.get(order=5)
        self.assertEqual(question.question_type, "FB")
        self.assertEqual(question.blank_answers, [["for", "for loop"], ["while"]])
        self.assertEqual(question.correct_option, "")

    def test_answer_lines_must_match_the_number_of_blanks(self):
        resp = self.client.post(
            self.add_url(), self.fb_data(blank_answers_text="for"))

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "has 2 blanks")
        self.assertEqual(self.test.questions.count(), 4)

    def test_a_prompt_with_no_blanks_takes_one_answer(self):
        resp = self.client.post(self.add_url(), self.fb_data(
            prompt="What keyword defines a function?",
            blank_answers_text="def"))

        self.assertEqual(resp.status_code, 302)

    def test_fill_in_the_blank_needs_answers(self):
        resp = self.client.post(
            self.add_url(), self.fb_data(blank_answers_text=""))
        self.assertContains(resp, "Give the answer for each blank.")

    def test_adding_a_matching_question(self):
        resp = self.client.post(self.add_url(), self.mt_data(
            [("list", "[1, 2]"), ("dict", "{'a': 1}")],
            match_extras_text="(1, 2)\n[1, 2]\n"))

        self.assertEqual(resp.status_code, 302)
        question = self.test.questions.get(order=5)
        self.assertEqual(
            question.match_pairs, [["list", "[1, 2]"], ["dict", "{'a': 1}"]])
        # An extra that is already a real match isn't added twice.
        self.assertEqual(question.match_extras, ["(1, 2)"])

    def test_matching_needs_two_pairs(self):
        resp = self.client.post(self.add_url(), self.mt_data([("list", "[]")]))
        self.assertContains(resp, "at least two pairs")

    def test_matching_rejects_a_half_filled_row(self):
        resp = self.client.post(self.add_url(), self.mt_data(
            [("list", "[]"), ("dict", "{}"), ("set", "")]))
        self.assertContains(resp, "needs both a term and its match")

    def test_matching_rejects_a_repeated_term(self):
        resp = self.client.post(self.add_url(), self.mt_data(
            [("list", "[]"), ("list", "{}")]))
        self.assertContains(resp, "same term on the left")

    def test_the_edit_page_is_prefilled(self):
        resp = self.client.get(
            reverse("edit_test_question", args=[self.fb.id]))
        self.assertContains(resp, "def\nreturn | return None")

        resp = self.client.get(
            reverse("edit_test_question", args=[self.mt.id]))
        self.assertContains(resp, 'value="&#x27;hi&#x27;"')

    def test_switching_type_drops_the_old_answer_key(self):
        resp = self.client.post(
            reverse("edit_test_question", args=[self.fb.id]),
            {"question_type": "SA", "prompt": "Explain.", "points": 2})

        self.assertEqual(resp.status_code, 302)
        self.fb.refresh_from_db()
        self.assertEqual(self.fb.blank_answers, [])

    def test_the_workbench_shows_blanks_and_the_key(self):
        resp = self.client.get(reverse("edit_test", args=[self.test.id]))
        self.assertContains(resp, '<span class="blank-slot">1</span>')
        self.assertContains(resp, "<code>return None</code>")
        self.assertContains(resp, "str &rarr; &#x27;hi&#x27;")

    def test_duplicating_copies_the_answer_keys(self):
        self.client.post(reverse("duplicate_test", args=[self.test.id]))
        copy = self.teacher.tests.exclude(id=self.test.id).get()

        fb = copy.questions.get(question_type="FB")
        mt = copy.questions.get(question_type="MT")
        self.assertEqual(fb.blank_answers, self.fb.blank_answers)
        self.assertEqual(mt.match_pairs, self.mt.match_pairs)
        self.assertEqual(mt.match_extras, ["None"])

    def test_csv_rows_of_the_new_types_are_refused_clearly(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        upload = SimpleUploadedFile(
            "q.csv", b"question_type,prompt\nFB,Loops use ___\n")
        resp = self.client.post(
            reverse("upload_test_csv", args=[self.test.id]),
            {"csv_file": upload}, follow=True)

        self.assertContains(resp, "added one at a time")
        self.assertEqual(self.test.questions.count(), 4)


class TakingTests(NewQuestionTypeTestCase):
    def test_blanks_render_as_inputs_inside_the_prompt(self):
        client = self.student_client()
        client.get(self.take_url())

        resp = client.get(self.question_url(3))
        self.assertContains(resp, f'name="question_{self.fb.id}_1"')
        self.assertContains(resp, f'name="question_{self.fb.id}_2"')
        self.assertNotContains(resp, "___")

    def test_typed_blanks_are_saved_and_shown_again(self):
        client = self.student_client()
        client.get(self.take_url())
        client.post(self.question_url(3), {
            f"question_{self.fb.id}_1": " def ",
            f"question_{self.fb.id}_2": '"><script>',
            "action": "next",
        })

        self.assertEqual(
            self.answer_for(self.fb).responses, ["def", '"><script>'])

        resp = client.get(self.question_url(3))
        self.assertContains(resp, 'value="def"')
        self.assertContains(resp, 'value="&quot;&gt;&lt;script&gt;"')

    def test_matching_offers_every_choice_once(self):
        client = self.student_client()
        client.get(self.take_url())

        resp = client.get(self.question_url(4))
        for choice in ["42", "True", "3.5", "None"]:
            self.assertContains(resp, f'<option value="{choice}"', count=4)

    def test_matching_order_is_stable_for_one_student(self):
        client = self.student_client()
        client.get(self.take_url())

        first = client.get(self.question_url(4)).context["match_choices"]
        again = client.get(self.question_url(4)).context["match_choices"]
        self.assertEqual(first, again)

    def test_a_match_that_isnt_offered_is_not_stored(self):
        client = self.student_client()
        self.answer_and_submit(client, mt=["42", "made up", "", "3.5"])

        self.assertEqual(
            self.answer_for(self.mt).responses, ["42", "", "", "3.5"])

    def test_review_counts_filled_parts(self):
        client = self.student_client()
        client.get(self.take_url())
        client.post(self.question_url(3), {
            f"question_{self.fb.id}_1": "def", "action": "next"})

        resp = client.get(reverse("take_test_review", args=[self.test.public_id]))
        self.assertContains(resp, "Filled 1 of 2 blanks")


class GradingTests(NewQuestionTypeTestCase):
    def test_all_blanks_right_earns_full_points(self):
        self.answer_and_submit(self.student_client(), fb=["DEF", "return  None"])
        self.assertEqual(self.answer_for(self.fb).points_awarded, 2)

    def test_half_the_blanks_earns_half(self):
        self.answer_and_submit(self.student_client(), fb=["def", "yield"])
        self.assertEqual(self.answer_for(self.fb).points_awarded, 1)

    def test_partial_credit_rounds_down(self):
        self.fb.points = 3
        self.fb.save()

        self.answer_and_submit(self.student_client(), fb=["def", "nope"])
        self.assertEqual(self.answer_for(self.fb).points_awarded, 1)

    def test_case_sensitive_blanks(self):
        self.fb.case_sensitive = True
        self.fb.save()

        self.answer_and_submit(self.student_client(), fb=["DEF", "return"])
        self.assertEqual(self.answer_for(self.fb).points_awarded, 1)

    def test_matching_scores_per_pair(self):
        self.answer_and_submit(
            self.student_client(), mt=["42", "'hi'", "None", "True"])
        # 2 of 4 pairs right, worth 4 points.
        self.assertEqual(self.answer_for(self.mt).points_awarded, 2)

    def test_untouched_questions_score_zero(self):
        self.answer_and_submit(self.student_client())
        self.assertEqual(self.answer_for(self.fb).points_awarded, 0)
        self.assertEqual(self.answer_for(self.mt).points_awarded, 0)

    def test_nothing_waits_in_the_grading_queue(self):
        self.answer_and_submit(
            self.student_client(), fb=["def", "return"], mt=["42"])
        resp = self.client.get(reverse("test_results", args=[self.test.id]))

        self.assertNotIn(self.fb, resp.context["questions_needing_grading"])
        self.assertNotIn(self.mt, resp.context["questions_needing_grading"])

    def test_editing_the_key_rescores_submitted_answers(self):
        self.answer_and_submit(self.student_client(), fb=["def", "yield"])
        self.assertEqual(self.answer_for(self.fb).points_awarded, 1)

        resp = self.client.post(
            reverse("edit_test_question", args=[self.fb.id]), {
                "question_type": "FB",
                "prompt": self.fb.prompt,
                "blank_answers_text": "def\nreturn | yield",
                "points": 2,
            }, follow=True)

        self.assertContains(resp, "1 student score updated")
        self.assertEqual(self.answer_for(self.fb).points_awarded, 2)

    def test_teacher_can_override_on_the_grading_screen(self):
        self.answer_and_submit(self.student_client(), fb=["dfe", "return"])
        answer = self.answer_for(self.fb)
        self.assertEqual(answer.points_awarded, 1)

        url = reverse("grade_test_question", args=[self.fb.id])
        resp = self.client.get(url)
        self.assertContains(resp, "dfe")
        self.assertContains(resp, "scored automatically")

        self.client.post(url, {f"points_{answer.id}": "2"})
        answer.refresh_from_db()
        self.assertEqual(answer.points_awarded, 2)

    def test_attempt_detail_marks_each_part(self):
        self.answer_and_submit(
            self.student_client(), fb=["def", "yield"],
            mt=["42", "'hi'", "None", "True"])
        attempt = TestAttempt.objects.get(student__google_sub=CLAIMS["sub"])

        resp = self.client.get(reverse("attempt_detail", args=[attempt.id]))
        self.assertContains(resp, "yield")
        self.assertContains(resp, "(return or return None)")
        self.assertContains(resp, "Adjust points")

    def test_another_teacher_cant_grade_it(self):
        self.client.force_login(self.other_teacher)
        resp = self.client.get(
            reverse("grade_test_question", args=[self.fb.id]))
        self.assertEqual(resp.status_code, 404)


class BlankRenderingTests(NewQuestionTypeTestCase):
    def test_blanks_inside_code_fences_are_replaced(self):
        html, count = render_markdown_with_blanks(
            "```python\nfor i in ___(3):\n```", lambda n: f"<BOX{n}>")

        self.assertEqual(count, 1)
        self.assertIn("<BOX1>", html)

    def test_teacher_markup_cannot_smuggle_inputs(self):
        html, _ = render_markdown_with_blanks(
            '<input name="x"> ___', lambda n: "[box]")

        self.assertNotIn("<input", html)
        self.assertIn("[box]", html)
