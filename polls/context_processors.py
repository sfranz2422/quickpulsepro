from .google_auth import google_sign_in_configured
from .students import get_current_student


def student_auth(request):
    """Makes the signed-in student available to every template."""
    return {
        "current_student": get_current_student(request),
        "google_sign_in_configured": google_sign_in_configured(),
    }
