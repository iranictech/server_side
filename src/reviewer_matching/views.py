"""Native reviewer recommendations for Janeway."""

from functools import wraps

from django.conf import settings
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from security.decorators import (
    editor_is_not_author,
    article_decision_not_made,
    editor_user_required,
)
from submission.models import Article
from review.models import ReviewerCOIAssessment

from reviewer_matching.permissions import (
    enforce_assign_reviewer_policy,
)
from reviewer_matching.services import get_internal_matches
from reviewer_matching.openalex import propose_article_topics


def require_scoped_article(view_func):
    """Check article journal scope before security decorators."""

    @wraps(view_func)
    def wrapper(request, article_id, *args, **kwargs):
        journal = getattr(request, "journal", None)

        if journal is None:
            raise Http404("Journal context is required.")

        get_object_or_404(
            Article,
            pk=article_id,
            journal=journal,
        )

        return view_func(
            request,
            *args,
            article_id=article_id,
            **kwargs,
        )

    return wrapper


@require_scoped_article
@editor_is_not_author
@article_decision_not_made
@editor_user_required
@require_GET
def suggestions_page(request, article_id):
    """Return internal reviewer suggestions for an article."""

    article = get_object_or_404(
        Article,
        pk=article_id,
        journal=request.journal,
    )

    enforce_assign_reviewer_policy(request, article)

    candidates = get_internal_matches(
        article,
        request.user,
    )

    # Show only the latest editorial decision; older rows stay in the
    # append-only database history. No decision implies invitation approval.
    candidate_ids = {
        item.get("account_id") for item in candidates if item.get("account_id")
    }
    latest = {}
    if candidate_ids:
        history = ReviewerCOIAssessment.objects.filter(
            article=article,
            reviewer_id__in=candidate_ids,
        ).order_by("-recorded_at", "-pk")
        for assessment in history:
            latest.setdefault(assessment.reviewer_id, assessment)

    for candidate in candidates:
        assessment = latest.get(candidate.get("account_id"))
        candidate["latest_coi_assessment"] = assessment

    return render(
        request,
        "reviewer_matching/suggestions.html",
        {
            "article": article,
            "candidates": candidates,
            "external_enabled": bool(
                getattr(
                    settings,
                    "REVIEWER_MATCHING_ALLOW_EXTERNAL_REQUESTS",
                    False,
                )
            ),
            "article_topics": propose_article_topics(article),
        },
    )
