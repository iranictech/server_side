"""Editorial COI assessment recorder for eligible internal reviewer accounts.

This append-only service does not clear a candidate automatically and is
not wired into Janeway invitation flows until a separate guarded rollout.
"""

from core.models import Account
from review.logic import get_reviewer_candidates
from review.models import ReviewerCOIAssessment
from submission.models import FrozenAuthor

from .identity import normalize_orcid


VALID_STATUSES = {
    ReviewerCOIAssessment.STATUS_CLEARED,
    ReviewerCOIAssessment.STATUS_CONFLICT,
    ReviewerCOIAssessment.STATUS_UNCERTAIN,
}


def create_coi_decision(article, *, editor, reviewer_id, status, rationale):
    """Create one immutable-in-workflow decision for a journal reviewer."""
    try:
        reviewer_pk = int(reviewer_id)
    except (ValueError, TypeError):
        raise ValueError("Invalid reviewer identifier.") from None

    if reviewer_pk < 1 or status not in VALID_STATUSES:
        raise ValueError("Invalid reviewer or COI status.")

    if not isinstance(rationale, str):
        raise ValueError("Editorial rationale is required.")

    rationale = rationale.strip()
    if not 10 <= len(rationale) <= 2000:
        raise ValueError("Editorial rationale must be 10–2000 characters.")

    reviewer = Account.objects.filter(pk=reviewer_pk, is_active=True).first()
    if reviewer is None:
        raise ValueError("Reviewer is not eligible for this journal.")

    candidates = get_reviewer_candidates(article, user=editor)
    if not candidates.filter(pk=reviewer.pk).exists():
        raise ValueError("Reviewer is not eligible for this article.")

    if article.author_accounts.filter(pk=reviewer.pk).exists():
        raise ValueError("An article author cannot be assessed as a reviewer.")

    frozen_authors = FrozenAuthor.objects.filter(article=article)
    if frozen_authors.filter(author=reviewer).exists():
        raise ValueError("An article author cannot be assessed as a reviewer.")

    # Janeway may store an author as a FrozenAuthor without an Account FK.
    reviewer_email = (reviewer.email or "").strip().casefold()
    reviewer_orcid = normalize_orcid(reviewer.orcid)
    author_emails = frozen_authors.values_list("frozen_email", flat=True)
    normalized_emails = {(email or "").strip().casefold() for email in author_emails}
    if reviewer_email and reviewer_email in normalized_emails:
        raise ValueError("A matching article-author email blocks COI assessment.")

    author_orcids = list(frozen_authors.values_list("frozen_orcid", flat=True))
    author_orcids.extend(article.author_accounts.values_list("orcid", flat=True))
    normalized_orcids = {normalize_orcid(value) for value in author_orcids}
    if reviewer_orcid and reviewer_orcid in normalized_orcids:
        raise ValueError("A matching article-author ORCID blocks COI assessment.")

    # Never overwrite previous decisions: the record history is the audit log.
    return ReviewerCOIAssessment.objects.create(
        article=article,
        reviewer=reviewer,
        assessed_by=editor,
        status=status,
        rationale=rationale,
    )
