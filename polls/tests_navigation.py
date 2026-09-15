from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from assessments.models import Test, TestAnswer, TestAttempt, TestQuestion
from polls.models import FlashCardSet, PollQuestion, Quiz, Student


class SectionPageTests(TestCase):
    """The dashboard is now a landing page; each tool lives on its own page."""

    def setUp(self):
        self.teacher = User.objects.create_user("teach", password="pw12345!x")
        self.other = User.objects.create_user("other", password="pw12345!x")
        self.client.force_login(self.teacher)

        self.question = PollQuestion.objects.create(
            teacher=self.teacher, question_text="Poll one",
            option_a="a", option_b="b", is_active=True)
        self.quiz = Quiz.objects.create(teacher=self.teacher, title="Quiz one")
        self.cards = FlashCardSet.objects.create(
            teacher=self.teacher, title="Cards one")
        self.test = Test.objects.create(teacher=self.teacher, title="Test one")

    # ---------- each section page shows only its own tool ----------

    def test_polling_page_lists_poll_questions_only(self):
        html = self.client.get(reverse("polling_home")).content.decode()
        self.assertIn("Poll one", html)
        self.assertNotIn("Quiz one", html)
        self.assertNotIn("Cards one", html)
        self.assertNotIn("Test one", html)

    def test_quizzes_page_lists_quizzes_only(self):
        html = self.client.get(reverse("quizzes_home")).content.decode()
        self.assertIn("Quiz one", html)
        self.assertNotIn("Poll one", html)
        self.assertNotIn("Cards one", html)

    def test_flashcards_page_lists_sets_only(self):
        html = self.client.get(reverse("flashcards_home")).content.decode()
        self.assertIn("Cards one", html)
        self.assertNotIn("Quiz one", html)

    def test_tests_page_lists_tests_only(self):
        html = self.client.get(reverse("tests_home")).content.decode()
        self.assertIn("Test one", html)
        self.assertNotIn("Quiz one", html)

    def test_section_pages_are_scoped_to_the_signed_in_teacher(self):
        self.client.force_login(self.other)
        for name in ["polling_home", "quizzes_home", "flashcards_home", "tests_home"]:
            html = self.client.get(reverse(name)).content.decode()
            for other_content in ["Poll one", "Quiz one", "Cards one", "Test one"]:
                self.assertNotIn(other_content, html, f"{name} leaked {other_content}")

    def test_section_pages_require_login(self):
        for name in ["polling_home", "quizzes_home", "flashcards_home", "tests_home"]:
            resp = Client().get(reverse(name))
            self.assertIn("/login/", resp["Location"], name)

    # ---------- the landing page ----------

    def test_dashboard_no_longer_lists_everything(self):
        html = self.client.get(reverse("dashboard")).content.decode()
        self.assertNotIn("Quiz one", html)
        self.assertNotIn("Cards one", html)

    def test_dashboard_links_to_all_four_sections(self):
        html = self.client.get(reverse("dashboard")).content.decode()
        for name in ["polling_home", "quizzes_home", "flashcards_home", "tests_home"]:
            self.assertIn(reverse(name), html)

    def test_dashboard_counts_each_tool(self):
        counts = self.client.get(reverse("dashboard")).context["counts"]
        self.assertEqual(counts, {
            "questions": 1, "quizzes": 1, "flashcard_sets": 1, "tests": 1})

    def test_dashboard_surfaces_the_live_poll_question(self):
        context = self.client.get(reverse("dashboard")).context
        self.assertEqual(context["active_question"], self.question)

    def test_dashboard_surfaces_open_tests(self):
        self.test.is_open = True
        self.test.save()
        context = self.client.get(reverse("dashboard")).context
        self.assertEqual(list(context["open_tests"]), [self.test])

    def test_dashboard_surfaces_tests_needing_grading(self):
        question = TestQuestion.objects.create(
            test=self.test, order=1, question_type="SA",
            prompt="Explain", points=3)
        student = Student.objects.create(
            google_sub="uid-1", email="a@b.org", full_name="Ada")
        attempt = TestAttempt.objects.create(
            test=self.test, student=student, submitted_at="2026-09-15 10:00:00Z")
        TestAnswer.objects.create(
            attempt=attempt, question=question, text_answer="Because")

        context = self.client.get(reverse("dashboard")).context
        self.assertEqual(list(context["needs_grading"]), [self.test])
        self.assertEqual(context["needs_grading"][0].ungraded, 1)

    def test_graded_work_stops_showing_up(self):
        question = TestQuestion.objects.create(
            test=self.test, order=1, question_type="SA", prompt="Explain", points=3)
        student = Student.objects.create(
            google_sub="uid-1", email="a@b.org", full_name="Ada")
        attempt = TestAttempt.objects.create(
            test=self.test, student=student, submitted_at="2026-09-15 10:00:00Z")
        TestAnswer.objects.create(
            attempt=attempt, question=question, text_answer="Because",
            points_awarded=3)

        context = self.client.get(reverse("dashboard")).context
        self.assertEqual(list(context["needs_grading"]), [])

    def test_unsubmitted_work_is_not_called_ungraded(self):
        """A student still working isn't something the teacher can act on."""
        question = TestQuestion.objects.create(
            test=self.test, order=1, question_type="SA", prompt="Explain", points=3)
        student = Student.objects.create(
            google_sub="uid-1", email="a@b.org", full_name="Ada")
        attempt = TestAttempt.objects.create(test=self.test, student=student)
        TestAnswer.objects.create(
            attempt=attempt, question=question, text_answer="half an answer")

        context = self.client.get(reverse("dashboard")).context
        self.assertEqual(list(context["needs_grading"]), [])

    def test_quiet_dashboard_says_so(self):
        self.question.is_active = False
        self.question.save()
        html = self.client.get(reverse("dashboard")).content.decode()
        self.assertIn("Nothing needs your attention", html)

    # ---------- nav highlighting ----------

    def test_nav_highlights_the_section_you_are_in(self):
        cases = [
            ("polling_home", [], "polling"),
            ("quizzes_home", [], "quizzes"),
            ("flashcards_home", [], "flashcards"),
            ("tests_home", [], "tests"),
            ("edit_test", [self.test.id], "tests"),
            ("test_results", [self.test.id], "tests"),
            ("create_question", [], "polling"),
            ("question_results", [self.question.id], "polling"),
        ]
        for name, args, expected in cases:
            context = self.client.get(reverse(name, args=args)).context
            self.assertEqual(context["active_section"], expected, name)

    def test_grading_page_is_a_tests_page_not_a_polling_one(self):
        """Its URL contains '/questions/', which a path-prefix check would
        wrongly read as belonging to polling."""
        question = TestQuestion.objects.create(
            test=self.test, order=1, question_type="SA", prompt="Explain")
        context = self.client.get(
            reverse("grade_test_question", args=[question.id])).context
        self.assertEqual(context["active_section"], "tests")

    def test_dashboard_highlights_nothing(self):
        context = self.client.get(reverse("dashboard")).context
        self.assertEqual(context["active_section"], "")

    def test_nav_is_hidden_from_signed_out_visitors(self):
        html = Client().get(reverse("home")).content.decode()
        self.assertNotIn(reverse("polling_home"), html)
