from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("dashboard/", views.dashboard, name="dashboard"),

    path("create_quiz/<int:teacher_id>", views.create_quiz, name="create_quiz"),
    path("upload_csv/<int:QuizID>/", views.upload_csv, name="upload_csv"),

    path("display_quiz/<uuid:public_id>/", views.display_quiz, name="display_quiz"),

    path("questions/create/", views.create_question, name="create_question"),
    path("questions/<int:question_id>/results/", views.question_results, name="question_results"),
    path(
        "questions/<int:question_id>/results/data/",
        views.question_results_data,
        name="question_results_data"
    ),

    path("student/<int:teacher_id>/", views.student_room, name="student_room"),
    path("student/<int:teacher_id>/submit/", views.submit_response, name="submit_response"),
    path(
        "start_quiz/<uuid:public_id>",
        views.start_quiz,
        name="start_quiz"
    ),
    path("student/", views.student_landing, name="student_landing"),

    path("student/signin/", views.student_sign_in, name="student_sign_in"),
    path(
        "student/signin/google/",
        views.student_google_callback,
        name="student_google_callback"
    ),
    path("student/signout/", views.student_sign_out, name="student_sign_out"),

    path(
        "poll/<uuid:public_id>/",
        views.poll_question_page,
        name="poll_question_page"
    ),
    path(
        "poll/<uuid:public_id>/submit/",
        views.submit_poll_answer,
        name="submit_poll_answer"
    ),
    path("register/", views.register_teacher, name="register_teacher"),
    path("delete_poll_question/<int:id>/teacher", views.delete_poll_question, name="delete_poll_question"),
    path("quiz_results/<int:quiz_id>/", views.quiz_results, name="quiz_results"),
    path(
        "download_quiz_csv_template/",
        views.download_quiz_csv_template,
        name="download_quiz_csv_template"
    ),
    path("delete_quiz/<int:quiz_id>/", views.delete_quiz, name="delete_quiz"),
    path(
        "poll_question/<int:question_id>/toggle/",
        views.toggle_poll_question_active,
        name="toggle_poll_question_active"
    ),
    path(
        "poll_question/<int:question_id>/clear/",
        views.clear_poll_responses,
        name="clear_poll_responses"
    ),
    path(
        "flashcards/create/<int:teacher_id>/",
        views.create_flashcard_set,
        name="create_flashcard_set"
    ),

    path(
        "flashcards/upload/<int:set_id>/",
        views.upload_flashcards,
        name="upload_flashcards"
    ),

    path(
        "flashcards/start/<uuid:public_id>/",
        views.start_flashcards,
        name="start_flashcards"
    ),

    path(
        "flashcards/display/<uuid:public_id>/",
        views.display_flashcards,
        name="display_flashcards"
    ),
    path(
        "flashcards/delete/<int:set_id>/",
        views.delete_flashcard_set,
        name="delete_flashcard_set"
    ),
    path(
        "flashcards/template/download/",
        views.download_flashcard_csv_template,
        name="download_flashcard_csv_template"
    ),
    path(
        "flashcards/results/<int:set_id>/",
        views.flashcard_results,
        name="flashcard_results"
    ),
    path(
        "flashcards/review/<uuid:public_id>/",
        views.review_thumbed_down_flashcards,
        name="review_thumbed_down_flashcards"
    ),
]
