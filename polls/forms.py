from cProfile import label

from django import forms
from .models import PollQuestion, PollResponse,QuizQuestion,Quiz
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.contrib.auth.forms import AuthenticationForm

class PollQuestionForm(forms.ModelForm):
    class Meta:
        model = PollQuestion

        fields = [
            "question_text",
            "option_a",
            "option_b",
            "option_c",
            "option_d",
        ]

        widgets = {
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

