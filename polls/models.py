import uuid

from django.db import models
from django.contrib.auth.models import User


class PollQuestion(models.Model):
    teacher = models.ForeignKey(User, on_delete=models.CASCADE)

    question_text = models.CharField(max_length=255)

    option_a = models.CharField(max_length=100)
    option_b = models.CharField(max_length=100)
    option_c = models.CharField(max_length=100, blank=True)
    option_d = models.CharField(max_length=100, blank=True)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

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

    selected_option = models.CharField(max_length=1)

    submitted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.question.question_text} - {self.selected_option}"


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