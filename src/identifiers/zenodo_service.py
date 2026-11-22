"""
Zenodo DOI integration service.

Phase 1: read-only eligibility validation.
No remote requests, DOI assignments, or database writes.
"""

from dataclasses import dataclass

from identifiers.models import Identifier
from identifiers.zenodo_models import ZenodoDeposit


@dataclass(frozen=True)
class ZenodoPreflightResult:
    eligible: bool
    reason: str
    article_id: int
    existing_dois: tuple
    existing_deposition_id: int | None = None


def check_zenodo_eligibility(article, *, is_sandbox=True):
    """
    Check whether an article may start a Zenodo deposit.

    This is a read-only check, not an authorization decision.
    Recheck under a database lock before any future mutation.
    """

    if article.pk is None:
        raise ValueError("Article must be saved")

    if article.journal_id is None:
        return ZenodoPreflightResult(
            False, "Article has no journal",
            article.pk, (),
        )

    # Include disabled identifiers: a DOI must never be
    # silently replaced just because it is disabled.
    dois = tuple(
        Identifier.objects.filter(
            article_id=article.pk,
            id_type="doi",
        ).order_by("pk").values_list(
            "identifier", flat=True
        )
    )

    if dois:
        return ZenodoPreflightResult(
            False, "Article already has a DOI",
            article.pk, dois,
        )

    existing = ZenodoDeposit.objects.filter(
        article_id=article.pk,
        is_sandbox=is_sandbox,
    ).first()

    if existing is not None:
        return ZenodoPreflightResult(
            False,
            "Article already has a Zenodo deposit record",
            article.pk,
            (),
            existing.deposition_id,
        )

    if not article.is_published:
        return ZenodoPreflightResult(
            False,
            "Article is not published",
            article.pk,
            (),
        )

    if article.date_published is None:
        return ZenodoPreflightResult(
            False,
            "Article has no publication date",
            article.pk,
            (),
        )

    if not article.license_id:
        return ZenodoPreflightResult(
            False,
            "Article has no publication license",
            article.pk,
            (),
        )

    if not article.frozenauthor_set.exists():
        return ZenodoPreflightResult(
            False,
            "Article has no frozen authors",
            article.pk,
            (),
        )

    if not article.pdfs.filter(
        public=True,
        is_remote=False,
    ).exists():
        return ZenodoPreflightResult(
            False,
            "Article has no PDF galley",
            article.pk,
            (),
        )

    return ZenodoPreflightResult(
        True,
        "Article passed preliminary Zenodo checks",
        article.pk,
        (),
    )
