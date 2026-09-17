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


class TestQuestion(models.Model):
    MULTIPLE_CHOICE = "MC"
    SHORT_ANSWER = "SA"

    QUESTION_TYPE_CHOICES = [
        (MULTIPLE_CHOICE, "Multiple Choice"),
        (SHORT_ANSWER, "Short Answer"),
    ]

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

    points = models.PositiveIntegerField(default=1)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "id"]

    @property
    def is_short_answer(self):
        return self.question_type == self.SHORT_ANSWER

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

    # Filled in automatically for multiple choice at submit time, and by the
    # teacher on the grading screen for short answers. None means ungraded.
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
        return not (self.selected_option or self.text_answer.strip())

    @property
    def is_correct_choice(self):
        """Only meaningful for multiple choice."""
        if self.question.is_short_answer:
            return None

        return (
            bool(self.selected_option)
            and self.selected_option == self.question.correct_option
        )

    def auto_grade(self):
        """Scores a multiple choice answer. Short answers are left for a human."""
        if self.question.is_short_answer:
            return

        self.points_awarded = (
            self.question.points if self.is_correct_choice else 0
        )

    def __str__(self):
        return f"{self.attempt.student} - {self.question}"
