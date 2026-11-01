from django.http import JsonResponse, Http404
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET

from security.decorators import (
    editor_user_required,
)
from submission.models import Article

from .services import get_internal_matches
from .permissions import enforce_assign_reviewer_policy


@require_GET
@editor_user_required
def internal_reviewer_matches(request, article_id):
    journal = getattr(request, "journal", None)
    if journal is None:
        raise Http404

    article = get_object_or_404(
        Article,
        pk=article_id,
        journal=journal,
    )

    enforce_assign_reviewer_policy(request, article)

    try:
        limit = int(request.GET.get("limit", "20"))
    except (TypeError, ValueError):
        return JsonResponse(
            {"error": "Invalid limit"},
            status=400,
        )

    if not 1 <= limit <= 100:
        return JsonResponse(
            {"error": "Limit must be between 1 and 100"},
            status=400,
        )

    matches = get_internal_matches(article, request.user, limit=limit)

    return JsonResponse(
        {
            "article_id": article.pk,
            "journal": journal.code,
            "source": "internal",
            "matching_method": "keyword_and_workload",
            "semantic_matching_enabled": False,
            "automatic_invitation": False,
            "coi_screening_complete": False,
            "count": len(matches),
            "candidates": matches,
        }
    )


# Combined reviewer matching.
# External network access is disabled unless explicitly configured.

import json

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST

from .combined import build_combined_matches
from .openalex import validate_public_topics, propose_article_topics


def _positive_limit(payload, name, default, maximum):
    value = payload.get(name, default)

    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError(f"{name} must be an integer between 1 and {maximum}")

    return value


@require_POST
@csrf_protect
@editor_user_required
def combined_reviewer_matches(request, article_id):
    journal = getattr(request, "journal", None)

    if journal is None:
        raise Http404

    article = get_object_or_404(
        Article,
        pk=article_id,
        journal=journal,
    )

    enforce_assign_reviewer_policy(request, article)

    if request.content_type != "application/json":
        return JsonResponse(
            {"error": "Content-Type must be application/json"},
            status=415,
        )

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse(
            {"error": "Invalid JSON body"},
            status=400,
        )

    if not isinstance(payload, dict):
        return JsonResponse(
            {"error": "Expected a JSON object"},
            status=400,
        )

    try:
        if "use_article_keywords" in payload:
            if payload["use_article_keywords"] is not True:
                raise ValueError("use_article_keywords must be true.")

            if "public_topics" in payload:
                raise ValueError("Manual topics cannot accompany article keywords.")

            if payload.get("public_topics_approved") is not True:
                return JsonResponse(
                    {"error": "Article keywords require explicit approval."},
                    status=400,
                )

            current_topics = propose_article_topics(article)

            if not current_topics:
                raise ValueError("No eligible article keywords are available.")

            approved_topics = payload.get("approved_article_topics")

            if (
                not isinstance(approved_topics, list)
                or approved_topics != current_topics
            ):
                return JsonResponse(
                    {
                        "error": (
                            "Article keywords have changed or were not "
                            "confirmed. Reload the page and approve again."
                        )
                    },
                    status=409,
                )

            # Only the exact reviewed snapshot may reach OpenAlex.
            payload["public_topics"] = current_topics

        topics = payload.get("public_topics", [])

        if topics:
            if payload.get("public_topics_approved") is not True:
                return JsonResponse(
                    {"error": "Public topics require explicit approval."},
                    status=400,
                )
            topics = validate_public_topics(topics)
        else:
            if topics != []:
                raise ValueError("Invalid public_topics")
            topics = []

        internal_limit = _positive_limit(payload, "internal_limit", 20, 100)
        external_limit = _positive_limit(payload, "external_limit", 15, 30)

    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    result = build_combined_matches(
        article,
        request.user,
        public_topics=topics,
        internal_limit=internal_limit,
        external_limit=external_limit,
        allow_external=getattr(
            settings,
            "REVIEWER_MATCHING_ALLOW_EXTERNAL_REQUESTS",
            False,
        ),
        allow_orcid_email=getattr(
            settings,
            "REVIEWER_MATCHING_ALLOW_ORCID_EMAIL_REQUESTS",
            False,
        ),
    )

    result["journal"] = journal.code

    return JsonResponse(result)
