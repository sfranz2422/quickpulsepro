from django.contrib import admin
from .models import PollQuestion, PollResponse, QuizQuestion,Quiz
from .models import QuizResponse, FlashCard,FlashCardSet



admin.site.register(PollQuestion)
admin.site.register(PollResponse)
admin.site.register(QuizQuestion)
admin.site.register(QuizResponse)
admin.site.register(FlashCard)
admin.site.register(FlashCardSet)

# admin.site.register(Quiz)

@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ("title", "public_id", "teacher", "created_at")
    readonly_fields = ("public_id",)
