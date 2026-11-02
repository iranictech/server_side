"""Optional, fail-closed editorial COI gate for reviewer invitations.

Default OFF. Enable only after the COI migration and rollout review.
"""

from django.conf import settings
from django.core.exceptions import PermissionDenied

from review.models import ReviewerCOIAssessment


def enforce_reviewer_invitation_coi(article, reviewer):
    """Require the latest manually recorded decision to be cleared."""
    if not getattr(settings, "REVIEWER_MATCHING_ENFORCE_COI_ON_INVITE", False):
        return

    if reviewer is None or reviewer.pk is None:
        raise PermissionDenied("A known reviewer account is required.")

    latest = (
        ReviewerCOIAssessment.objects.filter(article=article, reviewer=reviewer)
        .order_by("-recorded_at", "-pk")
        .first()
    )
    if latest is None or latest.status != ReviewerCOIAssessment.STATUS_CLEARED:
        raise PermissionDenied(
            "Editorial COI clearance is required before reviewer invitation."
        )
