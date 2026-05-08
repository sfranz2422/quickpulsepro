from django.contrib import admin
from .models import PollQuestion, PollResponse, QuizQuestion,Quiz


admin.site.register(PollQuestion)
admin.site.register(PollResponse)
admin.site.register(QuizQuestion)
admin.site.register(Quiz)
