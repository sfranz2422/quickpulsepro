import uuid

from django.db import models
from django.contrib.auth.models import User


# Max characters a student may type into a short answer poll response.
SHORT_ANSWER_MAX_LENGTH = 500


class Student(models.Model):
    """A student identified by Google Sign-In.

    Deliberately not a django.contrib.auth User: teacher accounts remain
    the only thing that can reach the teacher side of the app, and a
    student signing in gains no privileges beyond having their answers
    labelled with their name.
    """

    # Google's stable account id. Email addresses can change or be
    # reassigned; `sub` cannot, so identity hangs off it.
    google_sub = models.CharField(max_length=255, unique=True)

    email = models.EmailField()
    full_name = models.CharField(max_length=200, blank=True)
    picture_url = models.URLField(max_length=500, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["full_name", "email"]

    @property
    def display_name(self):
        return self.full_name or self.email

    def __str__(self):
        return self.display_name


class PollQuestion(models.Model):
    MULTIPLE_CHOICE = "MC"
    SHORT_ANSWER = "SA"

    QUESTION_TYPE_CHOICES = [
        (MULTIPLE_CHOICE, "Multiple Choice"),
        (SHORT_ANSWER, "Short Answer"),
    ]

    teacher = models.ForeignKey(User, on_delete=models.CASCADE)

    question_text = models.CharField(max_length=255)

    question_type = models.CharField(
        max_length=2,
        choices=QUESTION_TYPE_CHOICES,
        default=MULTIPLE_CHOICE
    )

    # Options are only used by multiple choice questions.
    option_a = models.CharField(max_length=100, blank=True)
    option_b = models.CharField(max_length=100, blank=True)
    option_c = models.CharField(max_length=100, blank=True)
    option_d = models.CharField(max_length=100, blank=True)

    # Controls whether this question shows in the teacher's student room.
    # The permanent per-question link works regardless of this flag.
    is_active = models.BooleanField(default=True)

    public_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False
    )

    # Bumped each time the teacher clears this question's responses, which
    # invalidates the "already answered" flag stored in student browsers.
    answer_round = models.PositiveIntegerField(default=1)

    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def is_short_answer(self):
        return self.question_type == self.SHORT_ANSWER

    def answer_session_key(self):
        """Session flag marking that this browser already answered."""
        # Round 1 keeps the original key so deploying this change does not
        # unlock students who answered before it shipped.
        if self.answer_round <= 1:
            return f"answered_question_{self.id}"

        return f"answered_question_{self.id}_round_{self.answer_round}"

    def __str__(self):
        return self.question_text


class Quiz(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    teacher = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="quizzes"
    )

    public_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False
    )

    def __str__(self):
        return self.title


class QuizQuestion(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="questions")
    question_text = models.CharField(max_length=255)
    option_a = models.CharField(max_length=100)
    option_b = models.CharField(max_length=100)
    option_c = models.CharField(max_length=100, blank=True)
    option_d = models.CharField(max_length=100, blank=True)
    correctAnswer = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.question_text


class QuizResponse(models.Model):
    quiz = models.ForeignKey(
        Quiz,
        on_delete=models.CASCADE,
        related_name="responses"
    )

    question = models.ForeignKey(
        QuizQuestion,
        on_delete=models.CASCADE,
        related_name="responses"
    )

    # Set when the student was signed in; anonymous answers leave it null.
    student = models.ForeignKey(
        "Student",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quiz_responses"
    )

    selected_option = models.CharField(max_length=1)

    is_correct = models.BooleanField()

    submitted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.quiz.title} - {self.question.question_text}"


class PollResponse(models.Model):
    question = models.ForeignKey(
        PollQuestion,
        on_delete=models.CASCADE,
        related_name="responses"
    )

    # Set when the student was signed in; anonymous answers leave it null.
    student = models.ForeignKey(
        "Student",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="poll_responses"
    )

    # Used by multiple choice questions.
    selected_option = models.CharField(max_length=1, blank=True)

    # Used by short answer questions.
    text_answer = models.TextField(blank=True)

    submitted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        answer = self.text_answer or self.selected_option
        return f"{self.question.question_text} - {answer}"


class FlashCardSet(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    teacher = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="flashcard_sets"
    )
    public_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class FlashCard(models.Model):
    flashcard_set = models.ForeignKey(
        FlashCardSet,
        on_delete=models.CASCADE,
        related_name="cards"
    )

    front = models.CharField(max_length=255)
    back = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.front


class FlashCardResponse(models.Model):
    flashcard_set = models.ForeignKey(
        FlashCardSet,
        on_delete=models.CASCADE,
        related_name="responses"
    )

    card = models.ForeignKey(
        FlashCard,
        on_delete=models.CASCADE,
        related_name="responses"
    )

    knew_it = models.BooleanField()
    session_key = models.CharField(max_length=40, blank=True)

    submitted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.flashcard_set.title} - {self.card.front}"
