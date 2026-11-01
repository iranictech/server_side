"""Read-only integration with the existing Janeway reviewer pool."""

from review.logic import get_reviewer_candidates
from submission.models import FrozenAuthor

from .ranking import rank_internal


def get_internal_matches(article, editor, limit=20):
    keywords = {
        keyword.word.strip().casefold()
        for keyword in article.keywords.all()
        if keyword.word and keyword.word.strip()
    }

    authors = list(
        FrozenAuthor.objects.filter(article=article).values(
            "author_id", "frozen_email", "frozen_orcid"
        )
    )

    author_ids = {row["author_id"] for row in authors if row["author_id"]}
    author_ids.update(article.author_accounts.values_list("pk", flat=True))

    author_emails = {
        row["frozen_email"].strip()
        for row in authors
        if row["frozen_email"] and row["frozen_email"].strip()
    }
    author_orcids = {
        row["frozen_orcid"].strip()
        for row in authors
        if row["frozen_orcid"] and row["frozen_orcid"].strip()
    }

    reviewers = get_reviewer_candidates(article, user=editor)

    if author_ids:
        reviewers = reviewers.exclude(pk__in=author_ids)
    if author_emails:
        reviewers = reviewers.exclude(email__in=author_emails)
    if author_orcids:
        reviewers = reviewers.exclude(orcid__in=author_orcids)

    results = []
    for reviewer in reviewers.distinct():
        interests = sorted(
            {
                interest.name.strip()
                for interest in reviewer.interest.all()
                if interest.name and interest.name.strip()
            }
        )

        matched = sorted(
            interest for interest in interests if interest.casefold() in keywords
        )

        results.append(
            {
                "account_id": reviewer.pk,
                "name": reviewer.full_name(),
                "source": "janeway",
                "research_interests": interests,
                "matched_keywords": matched,
                "active_reviews": getattr(reviewer, "active_reviews_count", None),
                "expertise_evidence": (
                    "exact_keyword_overlap" if matched else "insufficient_evidence"
                ),
                "coi_status": "not_fully_checked",
                "invitation_ready": False,
            }
        )

    ranked = rank_internal(results)
    return ranked[:limit]
