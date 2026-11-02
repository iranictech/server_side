"""Optional, fail-closed editorial COI gate for reviewer invitations.

Default OFF. Enable only after the COI migration and rollout review.
"""

from django.conf import settings
from django.core.exceptions import PermissionDenied


def enforce_reviewer_invitation_coi(article, reviewer):
    """Require the latest manually recorded decision to be cleared."""
    if not getattr(settings, "REVIEWER_MATCHING_ENFORCE_COI_ON_INVITE", False):
        return

    # Import Django models only after app initialization. review.logic and
    # review.forms are themselves loaded during core.models initialization.
    from review.models import ReviewerCOIAssessment
    from submission.models import FrozenAuthor

    from .identity import normalize_orcid

    if reviewer is None or reviewer.pk is None or not reviewer.is_active:
        raise PermissionDenied("An active reviewer account is required.")

    if article.author_accounts.filter(pk=reviewer.pk).exists():
        raise PermissionDenied("An article author cannot review the article.")

    authors = FrozenAuthor.objects.filter(article=article)
    if authors.filter(author=reviewer).exists():
        raise PermissionDenied("An article author cannot review the article.")

    candidate_email = (reviewer.email or "").strip().casefold()
    frozen_emails = authors.values_list("frozen_email", flat=True)
    normalized_emails = {(value or "").strip().casefold() for value in frozen_emails}
    if candidate_email and candidate_email in normalized_emails:
        raise PermissionDenied("Article-author email conflicts with reviewer.")

    candidate_orcid = normalize_orcid(reviewer.orcid)
    if candidate_orcid:
        author_orcids = list(authors.values_list("frozen_orcid", flat=True))
        author_orcids.extend(article.author_accounts.values_list("orcid", flat=True))
        if any(normalize_orcid(value) == candidate_orcid for value in author_orcids):
            raise PermissionDenied("Article-author ORCID conflicts with reviewer.")

    latest = (
        ReviewerCOIAssessment.objects.filter(article=article, reviewer=reviewer)
        .order_by("-recorded_at", "-pk")
        .first()
    )
    if latest is None or latest.status != ReviewerCOIAssessment.STATUS_CLEARED:
        raise PermissionDenied(
            "Editorial COI clearance is required before reviewer invitation."
        )
