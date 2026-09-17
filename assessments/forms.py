from django import forms

from .models import Test, TestQuestion


MARKDOWN_TEXTAREA = {
    "class": "form-control markdown-editor",
    "rows": 8,
}


class TestForm(forms.ModelForm):
    class Meta:
        model = Test

        fields = [
            "title",
            "instructions",
            "completion_message",
            "completion_link_url",
            "completion_link_label",
        ]

        labels = {
            "instructions": "Instructions for students (markdown)",
            "completion_message": "Finish screen message (markdown)",
            "completion_link_url": "Finish screen link",
            "completion_link_label": "Link button text",
        }

        help_texts = {
            "completion_message": "Shown after a student submits. Leave blank for none.",
            "completion_link_url": "Optional. Shows as a button, e.g. an online IDE exercise.",
        }

        widgets = {
            "title": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Test title",
            }),
            "instructions": forms.Textarea(attrs={
                **MARKDOWN_TEXTAREA,
                "rows": 5,
                "placeholder": "Optional. Shown before the questions.",
            }),
            "completion_message": forms.Textarea(attrs={
                **MARKDOWN_TEXTAREA,
                "rows": 5,
                "placeholder": (
                    "Nice work. Now head to the coding challenge and finish "
                    "question 3 before the end of the period."
                ),
            }),
            "completion_link_url": forms.URLInput(attrs={
                "class": "form-control",
                "placeholder": "https://replit.com/@you/exercise",
            }),
            "completion_link_label": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Go to the coding question",
            }),
        }

    def clean(self):
        cleaned_data = super().clean()

        url = (cleaned_data.get("completion_link_url") or "").strip()
        label = (cleaned_data.get("completion_link_label") or "").strip()

        if label and not url:
            self.add_error(
                "completion_link_url",
                "Add the link address, or clear the button text."
            )

        # A link with no wording still needs something on the button.
        if url and not label:
            cleaned_data["completion_link_label"] = "Continue"

        return cleaned_data


class TestQuestionForm(forms.ModelForm):
    class Meta:
        model = TestQuestion

        fields = [
            "question_type",
            "prompt",
            "option_a",
            "option_b",
            "option_c",
            "option_d",
            "correct_option",
            "points",
        ]

        labels = {
            "question_type": "Question Type",
            "prompt": "Question (markdown — code fences work)",
            "correct_option": "Correct Option",
        }

        widgets = {
            "question_type": forms.RadioSelect(attrs={
                "class": "form-check-input",
            }),
            "prompt": forms.Textarea(attrs={
                **MARKDOWN_TEXTAREA,
                "placeholder": "What does this code print?\n\n```python\nfor i in range(3):\n    print(i)\n```",
            }),
            "option_a": forms.TextInput(attrs={
                "class": "form-control", "placeholder": "Option A"}),
            "option_b": forms.TextInput(attrs={
                "class": "form-control", "placeholder": "Option B"}),
            "option_c": forms.TextInput(attrs={
                "class": "form-control", "placeholder": "Option C (optional)"}),
            "option_d": forms.TextInput(attrs={
                "class": "form-control", "placeholder": "Option D (optional)"}),
            "correct_option": forms.Select(
                choices=[("", "—")] + [(x, x) for x in "ABCD"],
                attrs={"class": "form-select"},
            ),
            "points": forms.NumberInput(attrs={
                "class": "form-control", "min": 1}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["question_type"].choices = TestQuestion.QUESTION_TYPE_CHOICES

        # Requiredness depends on the question type, so it is decided in
        # clean() rather than on the individual fields.
        for name in ("option_a", "option_b", "correct_option"):
            self.fields[name].required = False

    def clean_points(self):
        points = self.cleaned_data.get("points")

        if not points or points < 1:
            raise forms.ValidationError("A question must be worth at least 1 point.")

        return points

    def clean(self):
        cleaned_data = super().clean()
        question_type = cleaned_data.get("question_type")

        option_fields = ["option_a", "option_b", "option_c", "option_d"]

        if question_type == TestQuestion.SHORT_ANSWER:
            # A short answer question has no options to store.
            for name in option_fields:
                cleaned_data[name] = ""

            cleaned_data["correct_option"] = ""

            return cleaned_data

        for name, label in [("option_a", "Option A"), ("option_b", "Option B")]:
            if not (cleaned_data.get(name) or "").strip():
                self.add_error(
                    name,
                    f"{label} is required for a multiple choice question."
                )

        correct = (cleaned_data.get("correct_option") or "").strip().upper()

        if not correct:
            self.add_error(
                "correct_option",
                "Choose which option is correct."
            )
        else:
            offered = [
                letter for letter, field in zip("ABCD", option_fields)
                if (cleaned_data.get(field) or "").strip()
            ]

            if correct not in offered:
                self.add_error(
                    "correct_option",
                    f"Option {correct} is blank, so it cannot be the answer."
                )

            cleaned_data["correct_option"] = correct

        return cleaned_data


class TestCSVUploadForm(forms.Form):
    csv_file = forms.FileField(
        label="CSV File",
        widget=forms.FileInput(attrs={"class": "form-control"})
    )
