from django import forms
from .models import PollQuestion, PollResponse


class PollQuestionForm(forms.ModelForm):
    class Meta:
        model = PollQuestion
        fields = [
            'question_text',
            'option_a',
            'option_b',
            'option_c',
            'option_d',
                  ]


class PollResponseForm(forms.ModelForm):
    class Meta:
        model = PollResponse
        fields = ["selected_option"]