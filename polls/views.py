import uuid
from pydoc import describe

from django.contrib.auth.models import User
from django.db.models import Count
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import PollQuestion, FlashCard, FlashCardSet
from .forms import PollQuestionForm, CreateFlashCardSetForm
from .models import PollResponse
from .forms import SelectTeacherForm
from django.contrib import messages
from .forms import TeacherRegistrationForm
from django.contrib.auth import login
from polls.forms import TeacherLoginForm
import csv
import io
from django.shortcuts import render
from .models import QuizQuestion
from .models import Quiz
from polls.forms import CSVUploadForm
from polls.forms import CreateQuizForm
from .models import QuizResponse
import csv
from django.http import HttpResponse
from .models import FlashCardResponse
import random


@login_required
def dashboard(request):
    questions = PollQuestion.objects.filter(
        teacher=request.user
    ).order_by("-created_at")
    quizs = Quiz.objects.filter(
        teacher=request.user
    ).order_by("-created_at")
    flashcard_sets = FlashCardSet.objects.filter(
        teacher=request.user
    ).order_by("-created_at")
    return render(request, "dashboard.html", {
        "questions": questions, "quizs": quizs, "flashcard_sets": flashcard_sets,
    })


def delete_poll_question(request, id):
    question = get_object_or_404(
        PollQuestion,
        id=id,
        teacher=request.user
    )
    question.delete()
    messages.success(request, "Question deleted.")
    return redirect("dashboard")


@login_required
def create_question(request):
    if request.method == "POST":
        form = PollQuestionForm(request.POST)

        if form.is_valid():
            # deactivate old questions
            # only one question per teacher
            PollQuestion.objects.filter(
                teacher=request.user
            ).update(is_active=False)

            question = form.save(commit=False)
            question.teacher = request.user
            question.is_active = True
            question.save()

            return redirect("dashboard")
    else:
        form = PollQuestionForm()

    return render(request, "create_question.html", {
        "form": form
    })


def student_landing(request):
    if request.method == "POST":
        form = SelectTeacherForm(request.POST)

        if form.is_valid():
            teacher_id = form.cleaned_data["teacher_id"]

            return redirect("student_room", teacher_id=teacher_id)
    else:
        form = SelectTeacherForm()

    return render(request, "student_landing.html", {"form": form})


def student_room(request, teacher_id):
    # SELECT * FROM auth_user WHERE id = teacher_id;
    teacher = get_object_or_404(User, id=teacher_id)

    question = PollQuestion.objects.filter(
        teacher=teacher,
        is_active=True
    ).order_by("-created_at").first()

    return render(request, "student_room.html", {"teacher": teacher, "question": question})


def submit_response(request, teacher_id):
    # SELECT * FROM auth_user WHERE id = teacher_id;

    teacher = get_object_or_404(User, id=teacher_id)

    question = PollQuestion.objects.filter(
        teacher=teacher,
        is_active=True
    ).order_by("-created_at").first()

    if question is None:
        return redirect("student_room", teacher_id=teacher_id)

    session_key = f"answered_question_{question.id}"
    if request.session.get(session_key):
        messages.warning(request, "Question already answered.")

        return redirect(
            "student_room",
            teacher_id=teacher.id
        )

    if request.method == "POST":
        selected_option = request.POST.get("selected_option")
        if selected_option:
            PollResponse.objects.create(
                question=question,
                selected_option=selected_option
            )
            request.session[session_key] = True
            return render(request, "thank_you.html", {"teacher": teacher, "question": question})

    return redirect("student_room", teacher_id=teacher_id)


@login_required
def question_results(request, question_id):
    question = get_object_or_404(
        PollQuestion,
        id=question_id,
        teacher=request.user
    )

    total_responses = question.responses.count()

    options = [
        ("A", question.option_a),
        ("B", question.option_b),
        ("C", question.option_c),
        ("D", question.option_d),
    ]

    results = []

    for letter, text in options:
        if text:
            count = question.responses.filter(selected_option=letter).count()

            if total_responses > 0:
                percent = round((count / total_responses) * 100)
            else:
                percent = 0

            results.append({
                "letter": letter,
                "text": text,
                "count": count,
                "percent": percent,
            })

    return render(request, "results.html", {
        "question": question,
        "results": results,
        "total_responses": total_responses,
    })


def register_teacher(request):
    if request.method == "POST":
        form = TeacherRegistrationForm(request.POST)

        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Account created successfully.")
            return redirect("dashboard")
    else:
        form = TeacherRegistrationForm()

    return render(request, "register.html", {
        "form": form
    })


@login_required
def create_quiz(request, teacher_id):
    teacher = get_object_or_404(User, id=teacher_id)
    if request.method == "POST":
        form = CreateQuizForm(request.POST)
        if form.is_valid():
            # Create and retrieve the object in one step
            quiz = form.save(commit=False)
            quiz.teacher = teacher
            quiz.save()
            return redirect("upload_csv", QuizID=quiz.id)
    else:
        form = CreateQuizForm()
    return render(request, "create_quiz.html", {"form": form})


#
# @login_required
# def upload_csv(request, QuizID):
#     quiz = get_object_or_404(Quiz, id=QuizID)
#     EXPECTED_COLUMNS = 6  # Example: [index 0] to [index 6]
#
#     if request.method == "POST":
#         form = CSVUploadForm(request.POST, request.FILES)
#         if form.is_valid():
#             file = request.FILES['csv_file']
#
#             # 1. Simple extension check
#             if not file.name.endswith('.csv'):
#                 messages.error(request, "Please upload a valid .csv file.")
#                 return render(request, 'upload.html', {'form': form})
#
#             try:
#                 data_set = file.read().decode('UTF-8')
#                 io_string = io.StringIO(data_set)
#                 reader = csv.reader(io_string, delimiter=',', quotechar="|")
#                 next(reader, None)  # Skip header
#
#                 objs = []
#                 for row_idx, column in enumerate(reader, start=0):  # start=2 for actual file row number
#                     # 2. Skip empty rows
#                     if not any(column):
#                         continue
#
#                     # 3. Validate column count
#                     if len(column) < EXPECTED_COLUMNS:
#                         messages.error(request, f"Row {row_idx} is missing data (Expected {EXPECTED_COLUMNS} columns).")
#                         return render(request, 'upload.html', {'form': form})
#
#                     objs.append(QuizQuestion(
#                         quiz=quiz,
#                         question_text=column[0],
#                         option_a=column[1],
#                         option_b=column[2],
#                         option_c=column[3],
#                         option_d=column[4],
#                         correctAnswer=column[5]
#                     ))
#
#                 if objs:
#                     QuizQuestion.objects.bulk_create(objs)
#                     messages.success(request, f"Successfully uploaded {len(objs)} questions.")
#                     return redirect("dashboard")
#                 else:
#                     messages.warning(request, "The CSV file appeared to be empty.")
#
#             except Exception as e:
#                 messages.error(request, f"Error processing file: {str(e)}")
#     else:
#         form = CSVUploadForm()
#
#     return render(request, 'upload.html', {'form': form})

@login_required
def upload_csv(request, QuizID):
    quiz = get_object_or_404(Quiz, id=QuizID)

    required_columns = [
        "question_text",
        "option_a",
        "option_b",
        "option_c",
        "option_d",
        "correctAnswer",
    ]

    if request.method == "POST":
        form = CSVUploadForm(request.POST, request.FILES)

        if form.is_valid():
            file = request.FILES["csv_file"]

            if not file.name.endswith(".csv"):
                messages.error(request, "Please upload a valid .csv file.")
                return render(request, "upload.html", {"form": form})

            try:
                data_set = file.read().decode("UTF-8-sig")
                io_string = io.StringIO(data_set)

                reader = csv.DictReader(io_string)

                if reader.fieldnames is None:
                    messages.error(request, "The CSV file has no header row.")
                    return render(request, "upload.html", {"form": form})

                missing_columns = [
                    col for col in required_columns
                    if col not in reader.fieldnames
                ]

                if missing_columns:
                    messages.error(
                        request,
                        f"Missing required columns: {', '.join(missing_columns)}"
                    )
                    return render(request, "upload.html", {"form": form})

                objs = []

                for row_idx, row in enumerate(reader, start=2):
                    question_text = row.get("question_text", "").strip()
                    option_a = row.get("option_a", "").strip()
                    option_b = row.get("option_b", "").strip()
                    option_c = row.get("option_c", "").strip()
                    option_d = row.get("option_d", "").strip()
                    correct_answer = row.get("correctAnswer", "").strip().upper()

                    # Skip fully empty rows
                    if not any([
                        question_text,
                        option_a,
                        option_b,
                        option_c,
                        option_d,
                        correct_answer
                    ]):
                        continue

                    # Required fields for any question
                    if not question_text or not option_a or not option_b or not correct_answer:
                        messages.error(
                            request,
                            f"Row {row_idx} is missing question text, option A, option B, or correct answer."
                        )
                        return render(request, "upload.html", {"form": form})

                    # Make sure answer is valid
                    valid_answers = ["A", "B"]

                    if option_c:
                        valid_answers.append("C")

                    if option_d:
                        valid_answers.append("D")

                    if correct_answer not in valid_answers:
                        messages.error(
                            request,
                            f"Row {row_idx} has invalid correctAnswer '{correct_answer}'. "
                            f"Valid answers for this row are: {', '.join(valid_answers)}."
                        )
                        return render(request, "upload.html", {"form": form})

                    objs.append(QuizQuestion(
                        quiz=quiz,
                        question_text=question_text,
                        option_a=option_a,
                        option_b=option_b,
                        option_c=option_c,
                        option_d=option_d,
                        correctAnswer=correct_answer
                    ))

                if objs:
                    QuizQuestion.objects.bulk_create(objs)
                    messages.success(
                        request,
                        f"Successfully uploaded {len(objs)} questions."
                    )
                    return redirect("dashboard")
                else:
                    messages.warning(request, "The CSV file appeared to be empty.")

            except Exception as e:
                messages.error(request, f"Error processing file: {str(e)}")

    else:
        form = CSVUploadForm()

    return render(request, "upload.html", {"form": form})


def display_quiz(request, public_id):
    quiz = get_object_or_404(Quiz, public_id=public_id)

    question_order = request.session.get(
        f"quiz_{quiz.id}_question_order",
        []
    )

    questions = list(
        QuizQuestion.objects.filter(id__in=question_order)
    )

    # Preserve shuffled order
    questions.sort(
        key=lambda q: question_order.index(q.id)
    )

    if not questions:
        messages.warning(request, "This quiz has no questions yet.")
        return redirect("dashboard")

    session_quiz_key = f"quiz_{quiz.id}_current_index"
    session_correct_key = f"quiz_{quiz.id}_correct"
    session_wrong_key = f"quiz_{quiz.id}_wrong"

    if session_quiz_key not in request.session:
        request.session[session_quiz_key] = 0
        request.session[session_correct_key] = 0
        request.session[session_wrong_key] = 0

    current_index = request.session[session_quiz_key]

    if current_index >= len(questions):
        return render(request, "quiz_finished.html", {
            "quiz": quiz,
            "correct": request.session[session_correct_key],
            "wrong": request.session[session_wrong_key],
            "total": len(questions),
        })

    current_question = questions[current_index]

    if request.method == "POST":
        selected_option = request.POST.get("selected_option").upper()
        correct_answer = current_question.correctAnswer.strip().upper()

        if selected_option == correct_answer:
            request.session[session_correct_key] += 1
            is_correct = True
            messages.success(request, "Correct!")
        else:
            request.session[session_wrong_key] += 1
            is_correct = False
            correct_option = correct_answer
            correct_text = {
                "A": current_question.option_a,
                "B": current_question.option_b,
                "C": current_question.option_c,
                "D": current_question.option_d,
            }.get(correct_option, "Unknown")
            messages.error(
                request,
                f"Incorrect. The correct answer was: {correct_text}"
            )
            # messages.error(request, "Incorrect.")

        QuizResponse.objects.create(
            quiz=quiz,
            question=current_question,
            selected_option=selected_option,
            is_correct=is_correct
        )
        request.session[session_quiz_key] += 1

        return redirect("display_quiz", public_id=quiz.public_id)

    current_number = current_index + 1
    total_questions = len(questions)
    progress_percent = round((current_number / total_questions) * 100)

    return render(request, "display_quiz.html", {
        "quiz": quiz,
        "question": current_question,
        "current_number": current_number,
        "total_questions": total_questions,
        "progress_percent": progress_percent,
        "correct": request.session[session_correct_key],
        "wrong": request.session[session_wrong_key],
    })


def start_quiz(request, public_id):
    quiz = get_object_or_404(Quiz, public_id=public_id)

    questions = list(
        quiz.questions.all().values_list("id", flat=True)
    )

    random.shuffle(questions)

    # Store randomized order in session
    request.session[f"quiz_{quiz.id}_question_order"] = questions

    # Reset quiz progress
    request.session[f"quiz_{quiz.id}_current_index"] = 0
    request.session[f"quiz_{quiz.id}_correct"] = 0
    request.session[f"quiz_{quiz.id}_wrong"] = 0

    return redirect(
        "display_quiz",
        public_id=quiz.public_id
    )


@login_required
def quiz_results(request, quiz_id):
    quiz = get_object_or_404(
        Quiz,
        id=quiz_id,
        teacher=request.user
    )

    questions = quiz.questions.all().order_by("id")

    results = []

    for question in questions:
        total = question.responses.count()
        correct = question.responses.filter(is_correct=True).count()
        incorrect = question.responses.filter(is_correct=False).count()

        if total > 0:
            percent_correct = round((correct / total) * 100)
        else:
            percent_correct = 0

        results.append({
            "question": question,
            "total": total,
            "correct": correct,
            "incorrect": incorrect,
            "percent_correct": percent_correct,
        })

    return render(request, "quiz_results.html", {
        "quiz": quiz,
        "results": results,
    })


@login_required
def download_quiz_csv_template(request):
    response = HttpResponse(content_type='text/csv')

    response['Content-Disposition'] = (
        'attachment; filename="quiz_template.csv"'
    )

    writer = csv.writer(response)

    # Header row
    writer.writerow([
        'question_text',
        'option_a',
        'option_b',
        'option_c',
        'option_d',
        'correctAnswer'
    ])

    # Sample row
    writer.writerow([
        'What keyword defines a function in Python?',
        'func',
        'def',
        'function',
        'define',
        'B'
    ])

    return response


@login_required
def delete_quiz(request, quiz_id):
    quiz = get_object_or_404(
        Quiz,
        id=quiz_id,
        teacher=request.user
    )

    if request.method == "POST":
        quiz.delete()
        messages.success(request, "Quiz deleted.")
        return redirect("dashboard")

    return redirect("dashboard")


@login_required
def toggle_poll_question_active(request, question_id):
    question = get_object_or_404(
        PollQuestion,
        id=question_id,
        teacher=request.user
    )

    if request.method == "POST":
        if question.is_active:
            question.is_active = False
            question.save()
            messages.success(request, "Question deactivated.")
        else:
            # Optional: only allow one active polling question per teacher
            PollQuestion.objects.filter(
                teacher=request.user
            ).update(is_active=False)

            question.is_active = True
            question.save()
            messages.success(request, "Question activated.")

    return redirect("dashboard")


@login_required
def create_flashcard_set(request, teacher_id):
    teacher = get_object_or_404(User, id=teacher_id)

    if request.method == "POST":
        form = CreateFlashCardSetForm(request.POST)

        if form.is_valid():
            flashcard_set = form.save(commit=False)
            flashcard_set.teacher = teacher
            flashcard_set.save()

            return redirect(
                "upload_flashcards",
                set_id=flashcard_set.id
            )
    else:
        form = CreateFlashCardSetForm()

    return render(request, "create_flashcard_set.html", {
        "form": form
    })


@login_required
def upload_flashcards(request, set_id):
    flashcard_set = get_object_or_404(
        FlashCardSet,
        id=set_id,
        teacher=request.user
    )

    if request.method == "POST":
        form = CSVUploadForm(request.POST, request.FILES)

        if form.is_valid():
            file = request.FILES["csv_file"]

            data_set = file.read().decode("UTF-8-sig")
            io_string = io.StringIO(data_set)
            reader = csv.DictReader(io_string)

            objs = []

            for row_idx, row in enumerate(reader, start=2):
                front = row.get("front", "").strip()
                back = row.get("back", "").strip()

                if not front and not back:
                    continue

                if not front or not back:
                    messages.error(
                        request,
                        f"Row {row_idx} is missing front or back text."
                    )
                    return render(request, "upload.html", {"form": form})

                objs.append(FlashCard(
                    flashcard_set=flashcard_set,
                    front=front,
                    back=back
                ))

            if objs:
                FlashCard.objects.bulk_create(objs)
                messages.success(
                    request,
                    f"Successfully uploaded {len(objs)} flash cards."
                )
                return redirect("dashboard")

            messages.warning(request, "The CSV file appeared to be empty.")

    else:
        form = CSVUploadForm()

    return render(request, "upload.html", {"form": form})


def start_flashcards(request, public_id):
    flashcard_set = get_object_or_404(
        FlashCardSet,
        public_id=public_id
    )
    mode = request.GET.get("mode", "front")  # default

    request.session[f"flashcards_{flashcard_set.id}_mode"] = mode
    if not request.session.session_key:
        request.session.create()

    FlashCardResponse.objects.filter(
        flashcard_set=flashcard_set,
        session_key=request.session.session_key
    ).delete()

    request.session[f"flashcards_{flashcard_set.id}_index"] = 0

    return redirect(
        "display_flashcards",
        public_id=flashcard_set.public_id
    )


def display_flashcards(request, public_id):
    flashcard_set = get_object_or_404(
        FlashCardSet,
        public_id=public_id
    )
    mode_key = f"flashcards_{flashcard_set.id}_mode"

    if request.GET.get("mode") in ["front", "back"]:
        request.session[mode_key] = request.GET.get("mode")

    mode = request.session.get(mode_key, "front")
    cards = list(flashcard_set.cards.all().order_by("id"))
    if not cards:
        messages.warning(request, "This flash card set has no cards yet.")
        return redirect("dashboard")

    session_key = f"flashcards_{flashcard_set.id}_index"

    if session_key not in request.session:
        request.session[session_key] = 0
    if not request.session.session_key:
        request.session.create()
    current_index = request.session[session_key]
    progress_percent = round(((current_index + 1) / len(cards)) * 100)
    if request.method == "POST":
        action = request.POST.get("action")

        if action in ["thumbs_up", "thumbs_down"]:
            FlashCardResponse.objects.create(
                flashcard_set=flashcard_set,
                card=cards[current_index],
                knew_it=(action == "thumbs_up"),
                session_key=request.session.session_key
            )

            request.session[session_key] += 1

        return redirect(
            "display_flashcards",
            public_id=flashcard_set.public_id
        )

    if current_index >= len(cards):
        return render(request, "flashcards_finished.html", {
            "flashcard_set": flashcard_set,
            "total": len(cards)
        })

    current_card = cards[current_index]

    return render(request, "display_flashcards.html", {
        "flashcard_set": flashcard_set,
        "card": current_card,
        "current_number": current_index + 1,
        "total_cards": len(cards),
        "progress_percent": progress_percent,
        "mode": mode,
    })


@login_required
def delete_flashcard_set(request, set_id):
    flashcard_set = get_object_or_404(
        FlashCardSet,
        id=set_id,
        teacher=request.user
    )

    if request.method == "POST":
        flashcard_set.delete()
        messages.success(request, "Flash card set deleted.")

    return redirect("dashboard")


@login_required
def download_flashcard_csv_template(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="flashcard_template.csv"'

    writer = csv.writer(response)
    writer.writerow(["front", "back"])
    writer.writerow(["What does HTML stand for?", "HyperText Markup Language"])
    writer.writerow(["What does CSS do?", "Styles the page"])

    return response


@login_required
def flashcard_results(request, set_id):
    flashcard_set = get_object_or_404(
        FlashCardSet,
        id=set_id,
        teacher=request.user
    )

    cards = flashcard_set.cards.all().order_by("id")

    results = []

    for card in cards:
        total = card.responses.count()
        knew = card.responses.filter(knew_it=True).count()
        struggled = card.responses.filter(knew_it=False).count()

        if total > 0:
            percent_struggled = round((struggled / total) * 100)
        else:
            percent_struggled = 0

        results.append({
            "card": card,
            "total": total,
            "knew": knew,
            "struggled": struggled,
            "percent_struggled": percent_struggled,
        })

    return render(request, "flashcard_results.html", {
        "flashcard_set": flashcard_set,
        "results": results,
    })


def home(request):
    return render(request, "home.html")


def review_thumbed_down_flashcards(request, public_id):
    flashcard_set = get_object_or_404(
        FlashCardSet,
        public_id=public_id
    )

    thumbed_down_responses = FlashCardResponse.objects.filter(
        flashcard_set=flashcard_set,
        session_key=request.session.session_key,
        knew_it=False
    ).select_related("card")

    return render(request, "review_thumbed_down_flashcards.html", {
        "flashcard_set": flashcard_set,
        "thumbed_down_responses": thumbed_down_responses,
    })
