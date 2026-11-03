"""Read-only integration with the existing Janeway reviewer pool."""

from review.logic import get_reviewer_candidates
from submission.models import FrozenAuthor

from .identity import normalize_orcid
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
        row["frozen_email"].strip().casefold()
        for row in authors
        if row["frozen_email"] and row["frozen_email"].strip()
    }
    author_orcids = set()
    for row in authors:
        normalized_orcid = normalize_orcid(row["frozen_orcid"])
        if normalized_orcid:
            author_orcids.add(normalized_orcid)

    # Never suggest deactivated accounts, even if they retain reviewer roles.
    reviewers = get_reviewer_candidates(article, user=editor).filter(is_active=True)

    if author_ids:
        reviewers = reviewers.exclude(pk__in=author_ids)
    if author_emails:
        reviewers = reviewers.exclude(email__in=author_emails)
    if author_orcids:
        reviewers = reviewers.exclude(orcid__in=author_orcids)

    results = []
    for reviewer in reviewers.distinct():
        # Database exact-match filters are an optimization, not a substitute
        # for canonical author-identity exclusion.
        if reviewer.email and reviewer.email.strip().casefold() in author_emails:
            continue

        reviewer_orcid = normalize_orcid(reviewer.orcid)
        if reviewer_orcid and reviewer_orcid in author_orcids:
            continue

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
