import csv
import io

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from polls.students import get_current_student, student_required

from .forms import TestCSVUploadForm, TestForm, TestQuestionForm
from .models import Test, TestAnswer, TestAttempt, TestQuestion


# ---------------------------------------------------------------- authoring


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
        "attempt_count": test.attempts.count(),
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
        "attempt_count": test.attempts.count(),
        "show_question_form": True,
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


def _save_answers(attempt, questions, posted):
    for question in questions:
        raw = (posted.get(f"question_{question.id}") or "").strip()

        answer, _ = TestAnswer.objects.get_or_create(
            attempt=attempt, question=question)

        if question.is_short_answer:
            answer.text_answer = raw
            answer.selected_option = ""
        else:
            answer.selected_option = raw[:1].upper() if raw else ""
            answer.text_answer = ""

        answer.save()


@student_required
def take_test(request, public_id):
    test = get_object_or_404(Test, public_id=public_id)
    student = get_current_student(request)
    questions = list(test.questions.all())

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

    if request.method == "POST":
        _save_answers(attempt, questions, request.POST)

        if request.POST.get("action") == "submit":
            now = timezone.now()

            for answer in attempt.answers.select_related("question"):
                answer.auto_grade()

                if answer.points_awarded is not None:
                    answer.graded_at = now
                    answer.save(update_fields=["points_awarded", "graded_at"])

            attempt.submitted_at = now
            attempt.save(update_fields=["submitted_at"])

            messages.success(request, "Your test has been submitted.")
        else:
            messages.success(request, "Progress saved. You have not submitted yet.")

        return redirect("take_test", public_id=test.public_id)

    existing = _answers_by_question(attempt)

    rows = [
        {"question": question, "answer": existing.get(question.id)}
        for question in questions
    ]

    return render(request, "assessments/take_test.html", {
        "test": test,
        "attempt": attempt,
        "rows": rows,
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
    """Grades every student's answer to one short answer question at once."""
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
