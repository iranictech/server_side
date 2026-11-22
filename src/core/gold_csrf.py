from django.http import HttpResponse
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.cache import patch_cache_control
from django.views.csrf import csrf_failure as default_csrf_failure


def csrf_failure(request, reason=""):
    """
    Gold-specific CSRF failure presentation.

    Does not disable CSRF or retry rejected requests.
    Other journal routes retain Django's default handler.
    """

    path = request.path

    if not path.startswith("/ua/"):
        return default_csrf_failure(request, reason=reason)

    user = getattr(request, "user", None)
    authenticated = bool(
        user is not None
        and getattr(user, "is_authenticated", False)
    )

    if authenticated:
        url_name = "core_dashboard"
        label = "Go to Dashboard"
    else:
        url_name = "core_login"
        label = "Go to Login"

    destination = reverse(url_name)

    context = {
        "continue_url": destination,
        "continue_label": label,
    }

    # Deliberately render without request-bound context processors.
    # This must work even if request.journal is not populated yet.
    content = render_to_string(
        "gold_csrf_failure.html",
        context=context,
        request=None,
    )

    response = HttpResponse(
        content,
        status=403,
        content_type="text/html; charset=utf-8",
    )

    patch_cache_control(
        response,
        no_store=True,
        no_cache=True,
        must_revalidate=True,
    )

    return response
