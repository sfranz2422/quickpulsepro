from django.urls import path

from . import classroom_views, views


urlpatterns = [
    # Authoring
    path("tests/", views.tests_home, name="tests_home"),
    path("tests/new/", views.create_test, name="create_test"),
    path("tests/<int:test_id>/edit/", views.edit_test, name="edit_test"),
    path(
        "tests/<int:test_id>/settings/",
        views.update_test_settings,
        name="update_test_settings",
    ),
    path(
        "tests/<int:test_id>/questions/add/",
        views.add_test_question,
        name="add_test_question",
    ),
    path(
        "tests/questions/<int:question_id>/edit/",
        views.edit_test_question,
        name="edit_test_question",
    ),
    path(
        "tests/questions/<int:question_id>/delete/",
        views.delete_test_question,
        name="delete_test_question",
    ),
    path(
        "tests/<int:test_id>/upload/",
        views.upload_test_csv,
        name="upload_test_csv",
    ),
    path(
        "tests/template/download/",
        views.download_test_csv_template,
        name="download_test_csv_template",
    ),
    path(
        "tests/<int:test_id>/toggle/",
        views.toggle_test_open,
        name="toggle_test_open",
    ),
    path(
        "tests/<int:test_id>/duplicate/",
        views.duplicate_test,
        name="duplicate_test",
    ),
    path("tests/<int:test_id>/delete/", views.delete_test, name="delete_test"),

    # Reporting and grading
    path("tests/<int:test_id>/results/", views.test_results, name="test_results"),
    path(
        "tests/<int:test_id>/results/export/",
        views.export_test_scores,
        name="export_test_scores",
    ),
    path(
        "tests/attempts/<int:attempt_id>/",
        views.attempt_detail,
        name="attempt_detail",
    ),
    path(
        "tests/attempts/<int:attempt_id>/reopen/",
        views.reopen_attempt,
        name="reopen_attempt",
    ),
    path(
        "tests/questions/<int:question_id>/grade/",
        views.grade_test_question,
        name="grade_test_question",
    ),

    # Google Classroom
    path(
        "tests/<int:test_id>/classroom/",
        classroom_views.test_classroom,
        name="test_classroom",
    ),
    path(
        "tests/<int:test_id>/classroom/post/",
        classroom_views.post_test_to_classroom,
        name="post_test_to_classroom",
    ),
    path(
        "tests/classroom/connect/",
        classroom_views.classroom_connect,
        name="classroom_connect",
    ),
    path(
        "tests/classroom/callback/",
        classroom_views.classroom_callback,
        name="classroom_callback",
    ),
    path(
        "tests/classroom/disconnect/",
        classroom_views.classroom_disconnect,
        name="classroom_disconnect",
    ),

    # Students
    path("test/<uuid:public_id>/", views.take_test, name="take_test"),
    path(
        "test/<uuid:public_id>/q/<int:number>/",
        views.take_test_question,
        name="take_test_question",
    ),
    path(
        "test/<uuid:public_id>/review/",
        views.take_test_review,
        name="take_test_review",
    ),
]
