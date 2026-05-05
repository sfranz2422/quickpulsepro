from django.urls import path
from . import views


urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("questions/create/", views.create_question, name="create_question"),
    path("questions/<int:question_id>/results/", views.question_results, name="question_results"),

    path("student/<int:teacher_id>/", views.student_room, name="student_room"),
    path("student/<int:teacher_id>/submit/", views.submit_response, name="submit_response"),
]