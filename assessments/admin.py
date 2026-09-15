from django.contrib import admin

from .models import Test, TestAnswer, TestAttempt, TestQuestion


class TestQuestionInline(admin.TabularInline):
    model = TestQuestion
    extra = 0
    fields = ("order", "question_type", "prompt", "correct_option", "points")


@admin.register(Test)
class TestAdmin(admin.ModelAdmin):
    list_display = ("title", "teacher", "is_open", "created_at")
    list_filter = ("is_open",)
    readonly_fields = ("public_id",)
    inlines = [TestQuestionInline]


@admin.register(TestAttempt)
class TestAttemptAdmin(admin.ModelAdmin):
    list_display = ("test", "student", "status_label", "submitted_at")
    list_filter = ("test",)
    raw_id_fields = ("test", "student")


@admin.register(TestAnswer)
class TestAnswerAdmin(admin.ModelAdmin):
    list_display = ("attempt", "question", "points_awarded", "graded_at")
    raw_id_fields = ("attempt", "question")
