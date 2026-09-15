from django.contrib import admin
from .models import PollQuestion, PollResponse, QuizQuestion,Quiz
from .models import QuizResponse, FlashCard,FlashCardSet
from .models import Student



admin.site.register(PollQuestion)
admin.site.register(QuizQuestion)
admin.site.register(FlashCard)
admin.site.register(FlashCardSet)

# admin.site.register(Quiz)

@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ("title", "public_id", "teacher", "created_at")
    readonly_fields = ("public_id",)


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("display_name", "email", "created_at", "last_seen_at")
    search_fields = ("full_name", "email")
    readonly_fields = ("google_sub", "created_at", "last_seen_at")


@admin.register(PollResponse)
class PollResponseAdmin(admin.ModelAdmin):
    list_display = ("question", "student", "selected_option", "submitted_at")
    list_filter = ("submitted_at",)
    raw_id_fields = ("question", "student")


@admin.register(QuizResponse)
class QuizResponseAdmin(admin.ModelAdmin):
    list_display = ("quiz", "question", "student", "is_correct", "submitted_at")
    list_filter = ("is_correct", "submitted_at")
    raw_id_fields = ("quiz", "question", "student")
