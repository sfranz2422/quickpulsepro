from django.urls import path
from . import views


urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),

    path("create_quiz/<int:teacher_id>", views.create_quiz, name="create_quiz"),
    path("upload_csv/<int:QuizID>/", views.upload_csv, name="upload_csv"),


    path("display_quiz/<uuid:public_id>/", views.display_quiz, name="display_quiz"),

    path("questions/create/", views.create_question, name="create_question"),
    path("questions/<int:question_id>/results/", views.question_results, name="question_results"),

    path("student/<int:teacher_id>/", views.student_room, name="student_room"),
    path("student/<int:teacher_id>/submit/", views.submit_response, name="submit_response"),
path(
    "start_quiz/<uuid:public_id>",
    views.start_quiz,
    name="start_quiz"
),
    path("student/", views.student_landing, name="student_landing"),
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
]