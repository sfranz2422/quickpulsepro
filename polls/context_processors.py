from .google_auth import google_sign_in_configured
from .students import get_current_student


def student_auth(request):
    """Makes the signed-in student available to every template."""
    return {
        "current_student": get_current_student(request),
        "google_sign_in_configured": google_sign_in_configured(),
    }


# Which nav section each URL name belongs to. Explicit rather than matching on
# path prefixes, because "/tests/questions/3/grade/" would otherwise look like
# it belonged to polling.
SECTION_BY_URL_NAME = {
    "polling_home": "polling",
    "create_question": "polling",
    "question_results": "polling",
    "question_results_data": "polling",
    "toggle_poll_question_active": "polling",
    "clear_poll_responses": "polling",
    "delete_poll_question": "polling",

    "quizzes_home": "quizzes",
    "create_quiz": "quizzes",
    "upload_csv": "quizzes",
    "quiz_results": "quizzes",
    "delete_quiz": "quizzes",
    "download_quiz_csv_template": "quizzes",

    "flashcards_home": "flashcards",
    "create_flashcard_set": "flashcards",
    "upload_flashcards": "flashcards",
    "flashcard_results": "flashcards",
    "delete_flashcard_set": "flashcards",
    "download_flashcard_csv_template": "flashcards",

    "tests_home": "tests",
    "create_test": "tests",
    "edit_test": "tests",
    "add_test_question": "tests",
    "delete_test_question": "tests",
    "upload_test_csv": "tests",
    "download_test_csv_template": "tests",
    "toggle_test_open": "tests",
    "delete_test": "tests",
    "test_results": "tests",
    "export_test_scores": "tests",
    "attempt_detail": "tests",
    "reopen_attempt": "tests",
    "grade_test_question": "tests",
}


def active_section(request):
    """Highlights the nav item for whichever tool the page belongs to."""
    match = getattr(request, "resolver_match", None)
    url_name = match.url_name if match else None

    return {"active_section": SECTION_BY_URL_NAME.get(url_name, "")}
