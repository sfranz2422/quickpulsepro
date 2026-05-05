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