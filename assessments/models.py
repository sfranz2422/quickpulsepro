import random
import re
import uuid

from django.contrib.auth.models import User
from django.db import models

from polls.models import Student


class Test(models.Model):
    """A summative assessment.

    Kept separate from Quiz on purpose: quizzes stay an anonymous, retakeable
    review tool, while a Test requires a signed-in student and records who
    answered what.
    """

    teacher = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="tests"
    )

    title = models.CharField(max_length=200)

    # Markdown, shown to students on the cover of the test.
    instructions = models.TextField(blank=True)

    public_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False
    )

    # Students can only start or submit while the test is open.
    is_open = models.BooleanField(default=False)

    # Shown on the finish screen after a student submits. Markdown.
    completion_message = models.TextField(blank=True)

    # An optional button on that screen, for sending them somewhere next.
    completion_link_url = models.URLField(max_length=500, blank=True)
    completion_link_label = models.CharField(max_length=100, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def total_points(self):
        return sum(question.points for question in self.questions.all())

    @property
    def has_completion_screen(self):
        """True when the teacher has customised what students see at the end."""
        return bool(self.completion_message or self.completion_link_url)

    @property
    def has_short_answer(self):
        return self.questions.filter(
            question_type=TestQuestion.SHORT_ANSWER
        ).exists()

    def __str__(self):
        return self.title


# Three or more underscores in a fill in the blank prompt mark one blank.
BLANK_MARKER = re.compile(r"_{3,}")


def normalize_blank(text, case_sensitive=False):
    """How a typed blank is compared: outer spaces trimmed, runs of spaces
    collapsed, and case ignored unless the question says otherwise."""
    text = " ".join((text or "").split())
    return text if case_sensitive else text.casefold()


class TestQuestion(models.Model):
    MULTIPLE_CHOICE = "MC"
    SHORT_ANSWER = "SA"
    FILL_IN_BLANK = "FB"
    MATCHING = "MT"

    QUESTION_TYPE_CHOICES = [
        (MULTIPLE_CHOICE, "Multiple Choice"),
        (SHORT_ANSWER, "Short Answer"),
        (FILL_IN_BLANK, "Fill in the Blank"),
        (MATCHING, "Matching"),
    ]

    # Rows offered on the authoring form for a matching question.
    MAX_MATCH_PAIRS = 12

    test = models.ForeignKey(
        Test,
        on_delete=models.CASCADE,
        related_name="questions"
    )

    order = models.PositiveIntegerField(default=0)

    question_type = models.CharField(
        max_length=2,
        choices=QUESTION_TYPE_CHOICES,
        default=MULTIPLE_CHOICE
    )

    # Markdown. Code fences are supported and syntax highlighted.
    prompt = models.TextField()

    option_a = models.CharField(max_length=300, blank=True)
    option_b = models.CharField(max_length=300, blank=True)
    option_c = models.CharField(max_length=300, blank=True)
    option_d = models.CharField(max_length=300, blank=True)

    # Only meaningful for multiple choice.
    correct_option = models.CharField(max_length=1, blank=True)

    # Fill in the blank: one list of accepted answers per blank, in the order
    # the blanks appear in the prompt. [["def"], ["return", "return None"]]
    blank_answers = models.JSONField(default=list, blank=True)

    # Fill in the blank: whether "True" and "true" are different answers.
    case_sensitive = models.BooleanField(default=False)

    # Matching: [[left, right], ...]. Students pick a right for each left.
    match_pairs = models.JSONField(default=list, blank=True)

    # Matching: extra right-hand choices that match nothing.
    match_extras = models.JSONField(default=list, blank=True)

    points = models.PositiveIntegerField(default=1)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "id"]

    @property
    def is_short_answer(self):
        return self.question_type == self.SHORT_ANSWER

    @property
    def is_multiple_choice(self):
        return self.question_type == self.MULTIPLE_CHOICE

    @property
    def is_fill_in_blank(self):
        return self.question_type == self.FILL_IN_BLANK

    @property
    def is_matching(self):
        return self.question_type == self.MATCHING

    @property
    def is_auto_graded(self):
        return not self.is_short_answer

    @property
    def blank_count(self):
        """A prompt with no ___ in it gets one answer box underneath."""
        return max(1, len(BLANK_MARKER.findall(self.prompt)))

    @property
    def part_count(self):
        """Blanks or pairs: the units partial credit is divided over."""
        if self.is_fill_in_blank:
            return len(self.blank_answers)

        if self.is_matching:
            return len(self.match_pairs)

        return 1

    def answer_key(self):
        """Everything that decides an auto-graded score, for spotting edits."""
        return (
            self.correct_option,
            self.blank_answers,
            self.case_sensitive,
            self.match_pairs,
            self.points,
        )

    def match_choices(self, seed=""):
        """Every right-hand item once, shuffled so the order gives nothing away.

        The shuffle is seeded, so one student sees the same order every time
        they come back to the question.
        """
        choices = []

        for item in [right for _, right in self.match_pairs] + self.match_extras:
            if item not in choices:
                choices.append(item)

        random.Random(f"{self.id}-{seed}").shuffle(choices)
        return choices

    def options(self):
        """The (letter, text) pairs this question actually offers."""
        pairs = [
            ("A", self.option_a),
            ("B", self.option_b),
            ("C", self.option_c),
            ("D", self.option_d),
        ]

        return [(letter, text) for letter, text in pairs if text]

    def __str__(self):
        return self.prompt[:60]


class TestAttempt(models.Model):
    """One student's run at one test. At most one row per (test, student)."""

    test = models.ForeignKey(
        Test,
        on_delete=models.CASCADE,
        related_name="attempts"
    )

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="test_attempts"
    )

    started_at = models.DateTimeField(auto_now_add=True)

    # Null means still in progress. A teacher reopening an attempt clears it.
    submitted_at = models.DateTimeField(null=True, blank=True)

    reopened_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["student__full_name", "student__email"]
        constraints = [
            models.UniqueConstraint(
                fields=["test", "student"],
                name="one_attempt_per_student_per_test",
            )
        ]

    @property
    def is_submitted(self):
        return self.submitted_at is not None

    @property
    def earned_points(self):
        return sum(
            answer.points_awarded or 0
            for answer in self.answers.all()
        )

    @property
    def ungraded_answers(self):
        """Submitted short answers still waiting on a human."""
        return [
            answer for answer in self.answers.all()
            if answer.points_awarded is None
        ]

    @property
    def needs_grading(self):
        return self.is_submitted and bool(self.ungraded_answers)

    @property
    def status_label(self):
        if not self.is_submitted:
            return "In progress"

        if self.needs_grading:
            return "Awaiting grading"

        return "Graded"

    def __str__(self):
        return f"{self.student} - {self.test}"


class TestAnswer(models.Model):
    attempt = models.ForeignKey(
        TestAttempt,
        on_delete=models.CASCADE,
        related_name="answers"
    )

    question = models.ForeignKey(
        TestQuestion,
        on_delete=models.CASCADE,
        related_name="answers"
    )

    selected_option = models.CharField(max_length=1, blank=True)
    text_answer = models.TextField(blank=True)

    # Fill in the blank: what was typed in each blank, in order. Matching:
    # the right-hand item chosen for each left-hand item, in order.
    responses = models.JSONField(default=list, blank=True)

    # Filled in automatically at submit time for everything except short
    # answers, which the teacher grades by hand. None means ungraded.
    points_awarded = models.PositiveIntegerField(null=True, blank=True)

    graded_at = models.DateTimeField(null=True, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["question__order", "question__id"]
        constraints = [
            models.UniqueConstraint(
                fields=["attempt", "question"],
                name="one_answer_per_question_per_attempt",
            )
        ]

    @property
    def is_blank(self):
        return not (
            self.selected_option
            or self.text_answer.strip()
            or self.filled_count
        )

    @property
    def filled_count(self):
        """How many blanks or pairs have something in them."""
        return sum(1 for response in self.responses or [] if response.strip())

    def response_at(self, index):
        responses = self.responses or []
        return responses[index] if index < len(responses) else ""

    @property
    def is_correct_choice(self):
        """Only meaningful for multiple choice."""
        if not self.question.is_multiple_choice:
            return None

        return (
            bool(self.selected_option)
            and self.selected_option == self.question.correct_option
        )

    def blank_results(self):
        """One row per blank: what they typed, and whether it is accepted."""
        question = self.question
        rows = []

        for index, accepted in enumerate(question.blank_answers):
            given = self.response_at(index)
            wanted = {
                normalize_blank(option, question.case_sensitive)
                for option in accepted
            }

            rows.append({
                "number": index + 1,
                "given": given,
                "accepted": accepted,
                "correct": bool(given.strip())
                and normalize_blank(given, question.case_sensitive) in wanted,
            })

        return rows

    def match_results(self):
        """One row per pair: the left item, their pick, and the right one."""
        rows = []

        for index, (left, right) in enumerate(self.question.match_pairs):
            given = self.response_at(index)

            rows.append({
                "left": left,
                "given": given,
                "answer": right,
                "correct": given == right,
            })

        return rows

    def part_results(self):
        if self.question.is_fill_in_blank:
            return self.blank_results()

        if self.question.is_matching:
            return self.match_results()

        return []

    @property
    def correct_part_count(self):
        return sum(1 for row in self.part_results() if row["correct"])

    def auto_grade(self):
        """Scores everything but short answers, which are left for a human.

        Blanks and matching pairs earn partial credit: each correct part is
        worth points / parts, and the total is rounded down to whole points.
        """
        question = self.question

        if question.is_short_answer:
            return

        if question.is_multiple_choice:
            self.points_awarded = question.points if self.is_correct_choice else 0
            return

        parts = question.part_count

        self.points_awarded = (
            question.points * self.correct_part_count // parts if parts else 0
        )

    def __str__(self):
        return f"{self.attempt.student} - {self.question}"


# ---------------------------------------------------------- Google Classroom


class ClassroomConnection(models.Model):
    """A teacher's standing permission to post tests to their Google Classroom.

    Teachers only. Students sign in with the plain openid/email/profile they
    always have; the Classroom permissions are asked for separately, by the
    teacher, from a test's Classroom page.

    `refresh_token` is ENCRYPTED with a key derived from SECRET_KEY, which
    lives in Render's environment and not this database, so a copy of the
    database alone is not a working key to anyone's classes. The cost:
    changing SECRET_KEY makes every stored token unreadable, and each teacher
    has to press Connect again.
    """

    teacher = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="classroom_connection"
    )

    refresh_token = models.TextField()

    # The Google account that granted it, so the page can say which one.
    google_email = models.CharField(max_length=320, blank=True)

    connected_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.teacher} - {self.google_email}"


class ClassroomPost(models.Model):
    """One Google Classroom class a test was posted to.

    Several per test when several periods take it: each class gets its own
    Classroom assignment, because each class's grades have to go to
    coursework in that class. Google only lets an app grade coursework the
    app created, so posting from here is what makes sending grades possible.
    """

    test = models.ForeignKey(
        Test,
        on_delete=models.CASCADE,
        related_name="classroom_posts"
    )

    course_id = models.CharField(max_length=32)
    course_name = models.CharField(max_length=200, blank=True)

    # Classroom's id for the assignment, and its page in Classroom.
    work_id = models.CharField(max_length=32)
    url = models.URLField(max_length=500, blank=True)

    posted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["posted_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["test", "course_id"],
                name="one_classroom_post_per_class",
            )
        ]

    def __str__(self):
        return f"{self.test} - {self.course_name or self.course_id}"
