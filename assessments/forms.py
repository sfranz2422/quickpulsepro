from django import forms

from .models import BLANK_MARKER, Test, TestQuestion


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
            "case_sensitive",
            "points",
        ]

        labels = {
            "question_type": "Question Type",
            "case_sensitive": "Capitals matter (\"True\" is not \"true\")",
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
            "case_sensitive": forms.CheckboxInput(attrs={
                "class": "form-check-input"}),
            "points": forms.NumberInput(attrs={
                "class": "form-control", "min": 1}),
        }

    # Fill in the blank. Not model fields: they are parsed into lists in
    # clean() and stored as JSON.
    blank_answers_text = forms.CharField(
        label="Answers, one line per blank",
        required=False,
        widget=forms.Textarea(attrs={
            "class": "form-control font-monospace",
            "rows": 3,
            "placeholder": "def\nreturn | return None",
        }),
    )

    match_extras_text = forms.CharField(
        label="Extra choices that match nothing (optional, one per line)",
        required=False,
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 2,
        }),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["question_type"].choices = TestQuestion.QUESTION_TYPE_CHOICES

        # Requiredness depends on the question type, so it is decided in
        # clean() rather than on the individual fields.
        for name in ("option_a", "option_b", "correct_option"):
            self.fields[name].required = False

        pairs = list(self.instance.match_pairs or [])

        for index in range(TestQuestion.MAX_MATCH_PAIRS):
            left, right = pairs[index] if index < len(pairs) else ("", "")

            for side, value, placeholder in [
                ("left", left, "Term"),
                ("right", right, "Its match"),
            ]:
                self.fields[f"match_{side}_{index}"] = forms.CharField(
                    required=False,
                    max_length=300,
                    initial=value,
                    widget=forms.TextInput(attrs={
                        "class": "form-control",
                        "placeholder": placeholder,
                    }),
                )

        if self.instance.pk:
            self.fields["blank_answers_text"].initial = "\n".join(
                " | ".join(accepted)
                for accepted in self.instance.blank_answers
            )
            self.fields["match_extras_text"].initial = "\n".join(
                self.instance.match_extras)

    def match_rows(self):
        """(left field, right field) per row, for the template."""
        return [
            (self[f"match_left_{index}"], self[f"match_right_{index}"])
            for index in range(TestQuestion.MAX_MATCH_PAIRS)
        ]

    def clean_points(self):
        points = self.cleaned_data.get("points")

        if not points or points < 1:
            raise forms.ValidationError("A question must be worth at least 1 point.")

        return points

    def clean(self):
        cleaned_data = super().clean()
        question_type = cleaned_data.get("question_type")

        option_fields = ["option_a", "option_b", "option_c", "option_d"]

        # Only the current type's answer key is kept, so a question that
        # changed type doesn't carry a stale one around.
        if question_type != TestQuestion.MULTIPLE_CHOICE:
            for name in option_fields:
                cleaned_data[name] = ""

            cleaned_data["correct_option"] = ""

        if question_type != TestQuestion.FILL_IN_BLANK:
            cleaned_data["blank_answers"] = []
            cleaned_data["case_sensitive"] = False

        if question_type != TestQuestion.MATCHING:
            cleaned_data["match_pairs"] = []
            cleaned_data["match_extras"] = []

        if question_type == TestQuestion.SHORT_ANSWER:
            return cleaned_data

        if question_type == TestQuestion.FILL_IN_BLANK:
            self._clean_blanks(cleaned_data)
            return cleaned_data

        if question_type == TestQuestion.MATCHING:
            self._clean_matching(cleaned_data)
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

    def _clean_blanks(self, cleaned_data):
        prompt = cleaned_data.get("prompt") or ""
        blanks = max(1, len(BLANK_MARKER.findall(prompt)))

        lines = [
            line for line in
            (cleaned_data.get("blank_answers_text") or "").splitlines()
            if line.strip()
        ]

        answers = []

        for line in lines:
            accepted = [option.strip() for option in line.split("|")]
            accepted = [option for option in accepted if option]

            if accepted:
                answers.append(accepted)

        if not answers:
            self.add_error(
                "blank_answers_text",
                "Give the answer for each blank."
            )
        elif len(answers) != blanks:
            self.add_error(
                "blank_answers_text",
                f"The question has {blanks} blank{'s' if blanks != 1 else ''} "
                f"(each ___ is one) but {len(answers)} answer "
                f"line{'s' if len(answers) != 1 else ''}. Give one line per blank."
            )

        cleaned_data["blank_answers"] = answers

    def _clean_matching(self, cleaned_data):
        pairs = []
        half_filled = False

        for index in range(TestQuestion.MAX_MATCH_PAIRS):
            left = (cleaned_data.get(f"match_left_{index}") or "").strip()
            right = (cleaned_data.get(f"match_right_{index}") or "").strip()

            if left and right:
                pairs.append([left, right])
            elif left or right:
                half_filled = True

        if half_filled:
            self.add_error(
                None,
                "Each matching row needs both a term and its match."
            )

        if len(pairs) < 2:
            self.add_error(
                None,
                "A matching question needs at least two pairs."
            )

        lefts = [left for left, _ in pairs]

        if len(set(lefts)) != len(lefts):
            self.add_error(
                None,
                "Two rows have the same term on the left. Each term needs "
                "to be different so students can tell them apart."
            )

        rights = {right for _, right in pairs}

        extras = []

        for line in (cleaned_data.get("match_extras_text") or "").splitlines():
            line = line.strip()

            if line and line not in rights and line not in extras:
                extras.append(line)

        cleaned_data["match_pairs"] = pairs
        cleaned_data["match_extras"] = extras

    def save(self, commit=True):
        question = super().save(commit=False)

        question.blank_answers = self.cleaned_data.get("blank_answers", [])
        question.match_pairs = self.cleaned_data.get("match_pairs", [])
        question.match_extras = self.cleaned_data.get("match_extras", [])

        if commit:
            question.save()

        return question


class TestCSVUploadForm(forms.Form):
    csv_file = forms.FileField(
        label="CSV File",
        widget=forms.FileInput(attrs={"class": "form-control"})
    )
