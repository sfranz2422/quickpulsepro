import json

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from polls.models import PollQuestion, PollResponse


class ResultsFeedTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("teach", password="pw12345!x")
        self.other = User.objects.create_user("other", password="pw12345!x")
        self.client.force_login(self.teacher)

        self.short = PollQuestion.objects.create(
            teacher=self.teacher, question_text="One takeaway?",
            question_type="SA", is_active=True,
        )

    def feed(self, question, client=None):
        client = client or self.client
        return client.get(reverse("question_results_data", args=[question.id]))

    # ---------- the feed ----------

    def test_feed_groups_short_answers_with_stable_keys(self):
        for answer in ["Recursion", "recursion ", " RECURSION", "Loops"]:
            PollResponse.objects.create(question=self.short, text_answer=answer)

        data = json.loads(self.feed(self.short).content)

        self.assertEqual(data["total_responses"], 4)
        self.assertEqual(len(data["results"]), 2)

        first = data["results"][0]
        self.assertEqual(first["key"], "recursion")
        self.assertEqual(first["text"], "Recursion")
        self.assertEqual(first["count"], 3)
        self.assertEqual(first["percent"], 75)
        self.assertEqual(first["letter"], "")

    def test_key_is_stable_as_counts_change(self):
        PollResponse.objects.create(question=self.short, text_answer="Loops")
        before = json.loads(self.feed(self.short).content)["results"][0]["key"]

        PollResponse.objects.create(question=self.short, text_answer="loops")
        after = json.loads(self.feed(self.short).content)["results"][0]["key"]

        self.assertEqual(before, after)

    def test_feed_uses_option_letters_for_multiple_choice(self):
        mc = PollQuestion.objects.create(
            teacher=self.teacher, question_text="Pick", question_type="MC",
            option_a="Yes", option_b="No",
        )
        PollResponse.objects.create(question=mc, selected_option="A")

        data = json.loads(self.feed(mc).content)
        self.assertEqual([r["key"] for r in data["results"]], ["A", "B"])
        self.assertEqual(data["results"][0]["letter"], "A")

    def test_feed_with_no_responses(self):
        data = json.loads(self.feed(self.short).content)
        self.assertEqual(data, {"total_responses": 0, "results": []})

    def test_feed_matches_the_rendered_page(self):
        PollResponse.objects.create(question=self.short, text_answer="Loops")

        page = self.client.get(reverse("question_results", args=[self.short.id]))
        data = json.loads(self.feed(self.short).content)

        self.assertEqual(page.context["results"], data["results"])
        self.assertEqual(page.context["total_responses"], data["total_responses"])

    # ---------- access ----------

    def test_feed_requires_login(self):
        resp = self.feed(self.short, client=Client())
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp["Location"])

    def test_feed_is_scoped_to_the_owning_teacher(self):
        other_client = Client()
        other_client.force_login(self.other)
        self.assertEqual(self.feed(self.short, client=other_client).status_code, 404)

    # ---------- the page itself ----------

    def test_page_no_longer_reloads_itself(self):
        html = self.client.get(
            reverse("question_results", args=[self.short.id])).content.decode()
        self.assertNotIn("window.location.reload", html)
        self.assertIn("question_results_data", html.replace("/results/data/", "question_results_data"))

    def test_rows_carry_key_and_count_for_diffing(self):
        PollResponse.objects.create(question=self.short, text_answer="Loops")
        html = self.client.get(
            reverse("question_results", args=[self.short.id])).content.decode()
        self.assertIn('data-key="loops"', html)
        self.assertIn('data-count="1"', html)

    def test_student_text_is_escaped_in_the_page(self):
        PollResponse.objects.create(
            question=self.short, text_answer="<script>alert(1)</script>")
        html = self.client.get(
            reverse("question_results", args=[self.short.id])).content.decode()
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)
