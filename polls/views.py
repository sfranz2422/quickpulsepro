from django.contrib.auth.models import User
from django.db.models import Count
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import PollQuestion
from .forms import PollQuestionForm
from .models import PollResponse


@login_required
def dashboard(request):
    questions = PollQuestion.objects.filter(
        teacher=request.user
    ).order_by("-created_at")

    return render(request, "dashboard.html", {
        "questions": questions
    })


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


def student_room(request, teacher_id):
    # SELECT * FROM auth_user WHERE id = teacher_id;
    teacher = get_object_or_404(User,id=teacher_id)

    question = PollQuestion.objects.filter(
        teacher=teacher,
        is_active=True
    ).order_by("-created_at").first()

    return render(request,"student_room.html",{"teacher":teacher, "question":question})

def submit_response(request, teacher_id):
    # SELECT * FROM auth_user WHERE id = teacher_id;

    teacher = get_object_or_404(User,id=teacher_id)


    question = PollQuestion.objects.filter(
        teacher=teacher,
        is_active=True
    ).order_by("-created_at").first()

    if question is None:
        return redirect("student_room", teacher_id=teacher_id)

    if request.method == "POST":
        selected_option = request.POST.get("selected_option")
        if selected_option:
            PollResponse.objects.create(
                question=question,
                selected_option=selected_option
            )

            return render(request, "thank_you.html",{"teacher":teacher, "question":question})

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