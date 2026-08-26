from cProfile import label

from django import forms
from .models import PollQuestion, PollResponse, QuizQuestion, Quiz, FlashCardSet
from .models import SHORT_ANSWER_MAX_LENGTH
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.contrib.auth.forms import AuthenticationForm

class PollQuestionForm(forms.ModelForm):
    class Meta:
        model = PollQuestion

        fields = [
            "question_type",
            "question_text",
            "option_a",
            "option_b",
            "option_c",
            "option_d",
        ]

        labels = {
            "question_type": "Question Type",
            "question_text": "Question",
        }

        widgets = {
            "question_type": forms.RadioSelect(attrs={
                "class": "form-check-input"
            }),

            "question_text": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Enter question"
            }),

            "option_a": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Option A"
            }),

            "option_b": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Option B"
            }),

            "option_c": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Option C (optional)"
            }),

            "option_d": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Option D (optional)"
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Options A and B are only required for multiple choice questions,
        # so requiredness is decided in clean() instead of on the field.
        self.fields["option_a"].required = False
        self.fields["option_b"].required = False

        # Radio buttons should not offer a blank choice.
        self.fields["question_type"].choices = PollQuestion.QUESTION_TYPE_CHOICES

    def clean(self):
        cleaned_data = super().clean()
        question_type = cleaned_data.get("question_type")

        option_fields = ["option_a", "option_b", "option_c", "option_d"]

        if question_type == PollQuestion.SHORT_ANSWER:
            # A short answer question has no options to store.
            for field_name in option_fields:
                cleaned_data[field_name] = ""

        elif question_type == PollQuestion.MULTIPLE_CHOICE:
            required_options = [
                ("option_a", "Option A"),
                ("option_b", "Option B"),
            ]

            for field_name, label in required_options:
                if not (cleaned_data.get(field_name) or "").strip():
                    self.add_error(
                        field_name,
                        f"{label} is required for a multiple choice question."
                    )

        return cleaned_data


class ShortAnswerResponseForm(forms.Form):
    text_answer = forms.CharField(
        label="Your answer",
        max_length=SHORT_ANSWER_MAX_LENGTH,
        strip=True,
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 3,
            "maxlength": SHORT_ANSWER_MAX_LENGTH,
            "placeholder": "Type your answer",
            "required": "true",
        })
    )


class SelectTeacherForm(forms.Form):
    teacher_id = forms.IntegerField(
        label="",
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Enter teacher ID"
        })
    )

class PollResponseForm(forms.ModelForm):
    class Meta:
        model = PollResponse
        fields = ["selected_option"]

class TeacherRegistrationForm(UserCreationForm):

    username = forms.CharField(
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Username"
        })
    )

    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            "class": "form-control",
            "placeholder": "Email"
        })
    )

    password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            "class": "form-control",
            "placeholder": "Password"
        })
    )

    password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            "class": "form-control",
            "placeholder": "Repeat Password"
        })
    )

    class Meta:
        model = User

        fields = [
            "username",
            "email",
            "password1",
            "password2",
        ]
class TeacherLoginForm(AuthenticationForm):

    username = forms.CharField(
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Username"
        })
    )

    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            "class": "form-control",
            "placeholder": "Password"
        })
    )

class CreateQuizForm(forms.ModelForm):
    class Meta:
        model = Quiz
        fields = ["title", "description"]

        widgets = {
            "title": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Quiz Title",
                "required": "true",
            }),
            "description": forms.Textarea(attrs={
                "class": "form-control",
                "placeholder": "Quiz Description",
                "rows": "3",
                "required": "true",
            }),
        }

class CSVUploadForm(forms.Form):

    csv_file = forms.FileField(label="CSV File", widget=forms.FileInput(attrs={
            "class": "form-control",
    }))
class CreateFlashCardSetForm(forms.ModelForm):
    class Meta:
        model = FlashCardSet
        fields = ["title", "description"]

        widgets = {
            "title": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Flash Card Set Title"
            }),
            "description": forms.Textarea(attrs={
                "class": "form-control",
                "placeholder": "Description",
                "rows": 3
            }),
        }
