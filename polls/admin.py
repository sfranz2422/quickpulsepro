from django.contrib import admin
from .models import PollQuestion, PollResponse


admin.site.register(PollQuestion)
admin.site.register(PollResponse)