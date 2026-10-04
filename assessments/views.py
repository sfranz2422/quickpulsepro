import csv
import io
import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from polls.students import get_current_student, student_required

from .classroom import classroom_configured
from .forms import TestCSVUploadForm, TestForm, TestQuestionForm
from .models import Test, TestAnswer, TestAttempt, TestQuestion


# ---------------------------------------------------------------- authoring


@login_required
def tests_home(request):
    return render(request, "assessments/tests_home.html", {
        "tests": Test.objects.filter(teacher=request.user),
    })


@login_required
def create_test(request):
    if request.method == "POST":
        form = TestForm(request.POST)

        if form.is_valid():
            test = form.save(commit=False)
            test.teacher = request.user
            test.save()

            messages.success(request, "Test created. Now add some questions.")
            return redirect("edit_test", test_id=test.id)
    else:
        form = TestForm()

    return render(request, "assessments/create_test.html", {"form": form})


def _teacher_test(request, test_id):
    return get_object_or_404(Test, id=test_id, teacher=request.user)


@login_required
def edit_test(request, test_id):
    """The workbench for one test: its questions, and the two ways to add more."""
    test = _teacher_test(request, test_id)

    return render(request, "assessments/edit_test.html", {
        "test": test,
        "questions": test.questions.all(),
        "question_form": TestQuestionForm(),
        "csv_form": TestCSVUploadForm(),
        "settings_form": TestForm(instance=test),
        "attempt_count": test.attempts.count(),
        "classroom_on": classroom_configured(),
    })


@login_required
def update_test_settings(request, test_id):
    """Title, instructions, and what students see after they submit."""
    test = _teacher_test(request, test_id)

    if request.method != "POST":
        return redirect("edit_test", test_id=test.id)

    form = TestForm(request.POST, instance=test)

    if form.is_valid():
        form.save()
        messages.success(request, "Test settings saved.")
        return redirect("edit_test", test_id=test.id)

    return render(request, "assessments/edit_test.html", {
        "test": test,
        "questions": test.questions.all(),
        "question_form": TestQuestionForm(),
        "csv_form": TestCSVUploadForm(),
        "settings_form": form,
        "attempt_count": test.attempts.count(),
        "classroom_on": classroom_configured(),
        "show_settings": True,
    })


@login_required
def add_test_question(request, test_id):
    test = _teacher_test(request, test_id)

    if request.method != "POST":
        return redirect("edit_test", test_id=test.id)

    form = TestQuestionForm(request.POST)

    if form.is_valid():
        question = form.save(commit=False)
        question.test = test
        question.order = test.questions.count() + 1
        question.save()

        messages.success(request, "Question added.")
        return redirect("edit_test", test_id=test.id)

    # Re-render the workbench with this form's errors showing.
    return render(request, "assessments/edit_test.html", {
        "test": test,
        "questions": test.questions.all(),
        "question_form": form,
        "csv_form": TestCSVUploadForm(),
        "settings_form": TestForm(instance=test),
        "attempt_count": test.attempts.count(),
        "classroom_on": classroom_configured(),
        "show_question_form": True,
    })


def _rescore_after_edit(question, old_key):
    """Brings submitted scores in line with an edited question.

    `old_key` is question.answer_key() from before the edit. Returns how many
    answers changed. Answers on attempts still in progress are left alone:
    they are scored when the student submits.
    """
    answers = TestAnswer.objects.filter(
        question=question, attempt__submitted_at__isnull=False)

    now = timezone.now()
    changed = 0

    if question.is_auto_graded:
        if question.answer_key() == old_key:
            return 0

        for answer in answers:
            before = answer.points_awarded

            # Blank answers stay at 0, the same as at submit time.
            if answer.is_blank:
                answer.points_awarded = 0
            else:
                answer.auto_grade()

            if answer.points_awarded != before:
                answer.graded_at = now
                answer.save(update_fields=["points_awarded", "graded_at"])
                changed += 1

        return changed

    # Short answers are graded by hand, so only a grade above the new
    # maximum needs touching.
    for answer in answers.filter(points_awarded__gt=question.points):
        answer.points_awarded = question.points
        answer.graded_at = now
        answer.save(update_fields=["points_awarded", "graded_at"])
        changed += 1

    return changed


@login_required
def edit_test_question(request, question_id):
    question = get_object_or_404(
        TestQuestion, id=question_id, test__teacher=request.user)
    test = question.test

    answer_count = question.answers.count()
    old_type = question.question_type
    old_key = question.answer_key()

    if request.method == "POST":
        form = TestQuestionForm(request.POST, instance=question)

        if (
            form.is_valid()
            and answer_count
            and form.cleaned_data["question_type"] != old_type
        ):
            # Existing answers were written for the old type: a chosen letter
            # means nothing to a short answer question, and so on.
            form.add_error(
                "question_type",
                "Students have already answered this question, so its type "
                "can't change. Delete it and add a new one instead."
            )

        if form.is_valid():
            question = form.save()
            rescored = _rescore_after_edit(question, old_key)

            if rescored:
                messages.success(
                    request,
                    f"Question saved. {rescored} student "
                    f"score{'s' if rescored != 1 else ''} updated to match."
                )
            else:
                messages.success(request, "Question saved.")

            return redirect("edit_test", test_id=test.id)
    else:
        form = TestQuestionForm(instance=question)

    return render(request, "assessments/edit_question.html", {
        "test": test,
        "question": question,
        "question_form": form,
        "answer_count": answer_count,
    })


@login_required
@require_POST
def delete_test_question(request, question_id):
    question = get_object_or_404(
        TestQuestion, id=question_id, test__teacher=request.user)
    test = question.test

    question.delete()

    # Keep the numbering tidy after a removal.
    for position, remaining in enumerate(test.questions.all(), start=1):
        if remaining.order != position:
            remaining.order = position
            remaining.save(update_fields=["order"])

    messages.success(request, "Question deleted.")
    return redirect("edit_test", test_id=test.id)


# Accepted CSV headers. The first name is canonical; the rest are accepted so
# a CSV written for the quiz system imports without being rewritten.
CSV_ALIASES = {
    "prompt": ["prompt", "question_text", "question"],
    "option_a": ["option_a"],
    "option_b": ["option_b"],
    "option_c": ["option_c"],
    "option_d": ["option_d"],
    "correct_option": ["correct_option", "correctanswer", "correct_answer"],
    "question_type": ["question_type", "type"],
    "points": ["points"],
}


def _csv_value(row, field):
    for alias in CSV_ALIASES[field]:
        if alias in row and row[alias] is not None:
            return row[alias].strip()

    return ""


@login_required
def upload_test_csv(request, test_id):
    test = _teacher_test(request, test_id)

    if request.method != "POST":
        return redirect("edit_test", test_id=test.id)

    form = TestCSVUploadForm(request.POST, request.FILES)

    if not form.is_valid():
        messages.error(request, "Choose a CSV file to upload.")
        return redirect("edit_test", test_id=test.id)

    uploaded = request.FILES["csv_file"]

    if not uploaded.name.lower().endswith(".csv"):
        messages.error(request, "Please upload a file ending in .csv.")
        return redirect("edit_test", test_id=test.id)

    try:
        text = uploaded.read().decode("UTF-8-sig")
    except UnicodeDecodeError:
        messages.error(
            request,
            "That file isn't UTF-8 text. Re-save it from your spreadsheet as CSV."
        )
        return redirect("edit_test", test_id=test.id)

    reader = csv.DictReader(io.StringIO(text))

    if not reader.fieldnames:
        messages.error(request, "That CSV has no header row.")
        return redirect("edit_test", test_id=test.id)

    # Header matching is case-insensitive so Excel's capitalisation doesn't matter.
    reader.fieldnames = [name.strip().lower() for name in reader.fieldnames]

    if not any(alias in reader.fieldnames for alias in CSV_ALIASES["prompt"]):
        messages.error(
            request,
            "That CSV needs a 'prompt' column (or 'question_text')."
        )
        return redirect("edit_test", test_id=test.id)

    pending = []
    next_order = test.questions.count()

    for row_number, row in enumerate(reader, start=2):
        row = {key: (value or "") for key, value in row.items() if key}

        prompt = _csv_value(row, "prompt")
        option_a = _csv_value(row, "option_a")
        option_b = _csv_value(row, "option_b")
        option_c = _csv_value(row, "option_c")
        option_d = _csv_value(row, "option_d")
        correct = _csv_value(row, "correct_option").upper()
        raw_type = _csv_value(row, "question_type").upper()
        raw_points = _csv_value(row, "points")

        if not any([prompt, option_a, option_b, correct]):
            continue

        if not prompt:
            messages.error(request, f"Row {row_number} has no question text.")
            return redirect("edit_test", test_id=test.id)

        if raw_type in ("SA", "SHORT", "SHORT ANSWER"):
            question_type = TestQuestion.SHORT_ANSWER
        elif raw_type in ("MC", "MULTIPLE CHOICE", ""):
            # A row with no options and no answer is a short answer question,
            # even when the type column is missing entirely.
            question_type = (
                TestQuestion.MULTIPLE_CHOICE
                if (option_a and option_b)
                else TestQuestion.SHORT_ANSWER
            )
        elif raw_type in ("FB", "MT", "FILL IN THE BLANK", "MATCHING"):
            messages.error(
                request,
                f"Row {row_number} is a fill in the blank or matching "
                f"question. Those are added one at a time with the form "
                f"above, not by CSV."
            )
            return redirect("edit_test", test_id=test.id)
        else:
            messages.error(
                request,
                f"Row {row_number} has an unknown question type '{raw_type}'."
            )
            return redirect("edit_test", test_id=test.id)

        try:
            points = int(raw_points) if raw_points else 1
        except ValueError:
            messages.error(
                request,
                f"Row {row_number} has a non-numeric points value '{raw_points}'."
            )
            return redirect("edit_test", test_id=test.id)

        if points < 1:
            messages.error(
                request, f"Row {row_number} must be worth at least 1 point.")
            return redirect("edit_test", test_id=test.id)

        if question_type == TestQuestion.MULTIPLE_CHOICE:
            if not option_a or not option_b:
                messages.error(
                    request,
                    f"Row {row_number} is multiple choice but is missing option A or B."
                )
                return redirect("edit_test", test_id=test.id)

            offered = [
                letter for letter, text
                in zip("ABCD", [option_a, option_b, option_c, option_d])
                if text
            ]

            if correct not in offered:
                messages.error(
                    request,
                    f"Row {row_number} has correct answer '{correct}'. "
                    f"Valid answers for that row are: {', '.join(offered)}."
                )
                return redirect("edit_test", test_id=test.id)
        else:
            option_a = option_b = option_c = option_d = ""
            correct = ""

        next_order += 1

        pending.append(TestQuestion(
            test=test,
            order=next_order,
            question_type=question_type,
            prompt=prompt,
            option_a=option_a,
            option_b=option_b,
            option_c=option_c,
            option_d=option_d,
            correct_option=correct,
            points=points,
        ))

    if not pending:
        messages.warning(request, "That CSV had no question rows.")
        return redirect("edit_test", test_id=test.id)

    TestQuestion.objects.bulk_create(pending)
    messages.success(request, f"Added {len(pending)} questions.")

    return redirect("edit_test", test_id=test.id)


@login_required
def download_test_csv_template(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="test_template.csv"'

    writer = csv.writer(response)
    writer.writerow([
        "question_type", "prompt", "option_a", "option_b",
        "option_c", "option_d", "correct_option", "points",
    ])
    writer.writerow([
        "MC", "What keyword defines a function in Python?",
        "func", "def", "function", "define", "B", "1",
    ])
    writer.writerow([
        "SA", "Explain in your own words what a loop does.",
        "", "", "", "", "", "3",
    ])

    return response


@login_required
@require_POST
def toggle_test_open(request, test_id):
    test = _teacher_test(request, test_id)

    if not test.is_open and not test.questions.exists():
        messages.error(request, "Add at least one question before opening the test.")
        return redirect("edit_test", test_id=test.id)

    test.is_open = not test.is_open
    test.save(update_fields=["is_open"])

    messages.success(
        request,
        "Test is open. Students can take it now."
        if test.is_open else
        "Test is closed. Students can no longer start or submit."
    )

    return redirect("edit_test", test_id=test.id)


# Matches a title that already ends in "(copy)" or "(copy 3)".
COPY_SUFFIX = re.compile(r"\s*\(copy(?: \d+)?\)$")


def _copy_title(test, teacher):
    """A free title for a duplicate: 'Unit 3' -> 'Unit 3 (copy)' -> '(copy 2)'."""
    base = COPY_SUFFIX.sub("", test.title).strip() or test.title
    base = base[:180]

    taken = set(
        Test.objects.filter(teacher=teacher).values_list("title", flat=True))

    candidate = f"{base} (copy)"
    number = 2

    while candidate in taken:
        candidate = f"{base} (copy {number})"
        number += 1

    return candidate[:200]


@login_required
@require_POST
def duplicate_test(request, test_id):
    """Copies a test and its questions. Student work is not copied."""
    original = _teacher_test(request, test_id)

    copy = Test.objects.create(
        teacher=request.user,
        title=_copy_title(original, request.user),
        instructions=original.instructions,
        completion_message=original.completion_message,
        completion_link_url=original.completion_link_url,
        completion_link_label=original.completion_link_label,
        # A copy always starts closed, so duplicating a live test can never
        # accidentally publish a second one.
        is_open=False,
    )

    TestQuestion.objects.bulk_create([
        TestQuestion(
            test=copy,
            order=question.order,
            question_type=question.question_type,
            prompt=question.prompt,
            option_a=question.option_a,
            option_b=question.option_b,
            option_c=question.option_c,
            option_d=question.option_d,
            correct_option=question.correct_option,
            blank_answers=question.blank_answers,
            case_sensitive=question.case_sensitive,
            match_pairs=question.match_pairs,
            match_extras=question.match_extras,
            points=question.points,
        )
        for question in original.questions.all()
    ])

    messages.success(
        request,
        f'Copied to "{copy.title}". It has its own student link and is '
        f'closed until you open it.'
    )

    return redirect("edit_test", test_id=copy.id)


@login_required
@require_POST
def delete_test(request, test_id):
    test = _teacher_test(request, test_id)
    test.delete()

    messages.success(request, "Test deleted.")
    return redirect("dashboard")


# ------------------------------------------------------------ taking a test


def _answers_by_question(attempt):
    return {answer.question_id: answer for answer in attempt.answers.all()}


def _ordered_questions(test):
    return list(test.questions.all())


def _save_one_answer(attempt, question, posted):
    """Stores the answer to a single question. Called on every navigation."""
    raw = (posted.get(f"question_{question.id}") or "").strip()

    answer, _ = TestAnswer.objects.get_or_create(
        attempt=attempt, question=question)

    answer.text_answer = ""
    answer.selected_option = ""
    answer.responses = []

    if question.is_short_answer:
        answer.text_answer = raw
    elif question.is_fill_in_blank:
        answer.responses = [
            (posted.get(f"question_{question.id}_{number}") or "").strip()[:300]
            for number in range(1, question.blank_count + 1)
        ]
    elif question.is_matching:
        # Only an item the question actually offers can be stored.
        offered = set(question.match_choices())

        for number in range(1, len(question.match_pairs) + 1):
            picked = posted.get(f"question_{question.id}_{number}") or ""
            answer.responses.append(picked if picked in offered else "")
    else:
        answer.selected_option = raw[:1].upper() if raw else ""

    answer.save()


def _live_attempt(request, test):
    """The in-progress attempt for this student, or None if they can't work on it."""
    student = get_current_student(request)

    attempt = TestAttempt.objects.filter(test=test, student=student).first()

    if attempt is None or attempt.is_submitted or not test.is_open:
        return None

    return attempt


@student_required
def take_test(request, public_id):
    """Entry point: sorts out the attempt, then sends them to a question."""
    test = get_object_or_404(Test, public_id=public_id)
    student = get_current_student(request)
    questions = _ordered_questions(test)

    attempt = TestAttempt.objects.filter(test=test, student=student).first()

    # A finished attempt is read-only, open or closed.
    if attempt is not None and attempt.is_submitted:
        return render(request, "assessments/test_submitted.html", {
            "test": test,
            "attempt": attempt,
        })

    if not test.is_open:
        return render(request, "assessments/test_unavailable.html", {
            "test": test,
            "reason": "This test is not open right now.",
        })

    if not questions:
        return render(request, "assessments/test_unavailable.html", {
            "test": test,
            "reason": "This test doesn't have any questions yet.",
        })

    if attempt is None:
        attempt, _ = TestAttempt.objects.get_or_create(test=test, student=student)

    # Pick up where they left off: the first question with nothing in it.
    answers = _answers_by_question(attempt)

    for position, question in enumerate(questions, start=1):
        answer = answers.get(question.id)

        if answer is None or answer.is_blank:
            return redirect(
                "take_test_question",
                public_id=test.public_id,
                number=position,
            )

    # Everything is answered, so go straight to the review screen.
    return redirect("take_test_review", public_id=test.public_id)


@student_required
def take_test_question(request, public_id, number):
    """One question on its own page."""
    test = get_object_or_404(Test, public_id=public_id)
    attempt = _live_attempt(request, test)

    if attempt is None:
        return redirect("take_test", public_id=test.public_id)

    questions = _ordered_questions(test)

    if not 1 <= number <= len(questions):
        return redirect("take_test", public_id=test.public_id)

    question = questions[number - 1]
    answer = attempt.answers.filter(question=question).first()

    if request.method == "POST":
        # Every move saves first, so navigating can never lose an answer.
        _save_one_answer(attempt, question, request.POST)

        action = request.POST.get("action", "next")

        if action == "prev" and number > 1:
            return redirect(
                "take_test_question",
                public_id=test.public_id,
                number=number - 1,
            )

        if action == "review" or number == len(questions):
            return redirect("take_test_review", public_id=test.public_id)

        return redirect(
            "take_test_question",
            public_id=test.public_id,
            number=number + 1,
        )

    return render(request, "assessments/take_test_question.html", {
        "test": test,
        "attempt": attempt,
        "question": question,
        "answer": answer,
        "match_rows": [
            {"number": index, "left": left,
             "picked": answer.response_at(index - 1) if answer else ""}
            for index, (left, _) in enumerate(question.match_pairs, start=1)
        ],
        # Seeded by attempt, so each student keeps one order but neighbours
        # don't share it.
        "match_choices": question.match_choices(seed=attempt.id),
        "number": number,
        "total": len(questions),
        "progress_percent": round(number / len(questions) * 100),
        "is_first": number == 1,
        "is_last": number == len(questions),
    })


@student_required
def take_test_review(request, public_id):
    """The last screen: what's answered, what isn't, and the submit button."""
    test = get_object_or_404(Test, public_id=public_id)
    attempt = _live_attempt(request, test)

    if attempt is None:
        return redirect("take_test", public_id=test.public_id)

    questions = _ordered_questions(test)
    answers = _answers_by_question(attempt)

    rows = []

    for position, question in enumerate(questions, start=1):
        answer = answers.get(question.id)

        rows.append({
            "number": position,
            "question": question,
            "answer": answer,
            "answered": answer is not None and not answer.is_blank,
        })

    if request.method == "POST":
        now = timezone.now()

        for question in questions:
            answer, _ = TestAnswer.objects.get_or_create(
                attempt=attempt, question=question)

            if answer.is_blank:
                # Nothing written is worth nothing. The teacher can still
                # change it on the grading screen.
                answer.points_awarded = 0
            else:
                answer.auto_grade()

            if answer.points_awarded is not None:
                answer.graded_at = now

            answer.save()

        attempt.submitted_at = now
        attempt.save(update_fields=["submitted_at"])

        messages.success(request, "Your test has been submitted.")
        return redirect("take_test", public_id=test.public_id)

    return render(request, "assessments/take_test_review.html", {
        "test": test,
        "attempt": attempt,
        "rows": rows,
        "unanswered": [row["number"] for row in rows if not row["answered"]],
    })


# ---------------------------------------------------------------- reporting


@login_required
def test_results(request, test_id):
    test = _teacher_test(request, test_id)

    attempts = (
        test.attempts
        .select_related("student")
        .prefetch_related("answers__question")
    )

    total_points = test.total_points

    rows = []

    for attempt in attempts:
        earned = attempt.earned_points

        rows.append({
            "attempt": attempt,
            "earned": earned,
            "percent": round(earned / total_points * 100) if total_points else 0,
        })

    ungraded = [
        question for question in test.questions.all()
        if question.is_short_answer
        and question.answers.filter(
            points_awarded__isnull=True,
            attempt__submitted_at__isnull=False,
        ).exists()
    ]

    return render(request, "assessments/test_results.html", {
        "test": test,
        "rows": rows,
        "total_points": total_points,
        "questions_needing_grading": ungraded,
        "submitted_count": sum(1 for row in rows if row["attempt"].is_submitted),
        "classroom_on": classroom_configured(),
    })


@login_required
def attempt_detail(request, attempt_id):
    attempt = get_object_or_404(
        TestAttempt, id=attempt_id, test__teacher=request.user)

    existing = _answers_by_question(attempt)

    rows = [
        {"question": question, "answer": existing.get(question.id)}
        for question in attempt.test.questions.all()
    ]

    return render(request, "assessments/attempt_detail.html", {
        "test": attempt.test,
        "attempt": attempt,
        "rows": rows,
        "total_points": attempt.test.total_points,
    })


@login_required
def grade_test_question(request, question_id):
    """Grades every student's answer to one question at once.

    Short answers come here to be graded. Auto-graded questions can come here
    too, to override a score, e.g. credit for a misspelled blank.
    """
    question = get_object_or_404(
        TestQuestion, id=question_id, test__teacher=request.user)

    answers = list(
        TestAnswer.objects
        .filter(question=question, attempt__submitted_at__isnull=False)
        .select_related("attempt__student")
    )

    if request.method == "POST":
        now = timezone.now()
        graded = 0

        for answer in answers:
            raw = request.POST.get(f"points_{answer.id}", "").strip()

            if raw == "":
                continue

            try:
                points = int(raw)
            except ValueError:
                continue

            points = max(0, min(points, question.points))

            answer.points_awarded = points
            answer.graded_at = now
            answer.save(update_fields=["points_awarded", "graded_at"])
            graded += 1

        messages.success(request, f"Graded {graded} answers.")
        return redirect("test_results", test_id=question.test.id)

    return render(request, "assessments/grade_question.html", {
        "test": question.test,
        "question": question,
        "answers": answers,
    })


@login_required
@require_POST
def reopen_attempt(request, attempt_id):
    attempt = get_object_or_404(
        TestAttempt, id=attempt_id, test__teacher=request.user)

    attempt.submitted_at = None
    attempt.reopened_count += 1
    attempt.save(update_fields=["submitted_at", "reopened_count"])

    messages.success(
        request,
        f"Reopened for {attempt.student.display_name}. "
        f"Their previous answers are still there."
    )

    return redirect("test_results", test_id=attempt.test.id)


@login_required
def export_test_scores(request, test_id):
    test = _teacher_test(request, test_id)
    questions = list(test.questions.all())

    response = HttpResponse(content_type="text/csv")
    filename = f"{test.title[:40].replace(' ', '_')}_scores.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)

    writer.writerow(
        ["student", "email", "status", "submitted_at", "points", "possible", "percent"]
        + [f"Q{index}" for index, _ in enumerate(questions, start=1)]
    )

    total_points = test.total_points

    attempts = (
        test.attempts
        .select_related("student")
        .prefetch_related("answers__question")
    )

    for attempt in attempts:
        by_question = _answers_by_question(attempt)
        earned = attempt.earned_points

        writer.writerow([
            attempt.student.display_name,
            attempt.student.email,
            attempt.status_label,
            attempt.submitted_at.strftime("%Y-%m-%d %H:%M") if attempt.submitted_at else "",
            earned,
            total_points,
            round(earned / total_points * 100) if total_points else 0,
        ] + [
            (by_question.get(question.id).points_awarded
             if by_question.get(question.id)
             and by_question.get(question.id).points_awarded is not None
             else "")
            for question in questions
        ])

    return response
