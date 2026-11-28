"""
Production metadata and preliminary eligibility.

No external API requests.
No DOI registration.
No Sandbox modifications.
"""

import re
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction

from identifiers.models import Identifier, CrossrefStatus
from identifiers.zenodo_models import ZenodoDeposit

from identifiers.zenodo_metadata import (
    normalize_text,
    map_author,
    resolve_zenodo_license,
)

from identifiers.zenodo_sandbox import (
    journal_article_metadata,
)

from identifiers.zenodo_pdf import (
    open_public_article_pdf,
)

from submission.models import Article
from identifiers.zenodo_journal_policy import (
    zenodo_enabled,
    default_doi_provider,
    zenodo_archive_enabled,
)


class ProductionMetadataError(ValueError):
    pass


DOI_PATTERN = re.compile(
    r"10\.\d{4,9}/[^\s]+"
)


@dataclass(frozen=True)
class ProductionEligibility:

    eligible: bool
    reason: str
    doi: str | None = None
    mode: str | None = None


def check_production_eligibility(
    article, *, check_existing=True
):

    def reject(reason):
        return ProductionEligibility(False, reason)

    if article.pk is None:
        return reject("Article must be saved")

    if article.pk == 40:
        return reject("Demo article is excluded")

    if not article.journal_id:
        return reject("Article has no journal")

    if not article.is_published:
        return reject("Article is not published")

    if not article.date_published:
        return reject("Publication date is missing")

    if not article.license_id:
        return reject("Publication license is missing")

    if not article.frozenauthor_set.exists():
        return reject("Article has no frozen authors")

    if not article.pdfs.filter(
        public=True,
        is_remote=False,
    ).exists():
        return reject("Public local PDF is missing")

    if check_existing and ZenodoDeposit.objects.filter(
        article_id=article.pk,
        is_sandbox=False,
    ).exists():
        return reject("Production deposit already exists")

    identifiers = list(
        Identifier.objects.filter(
            article_id=article.pk,
            id_type="doi",
        ).order_by("pk")
    )

    if not zenodo_enabled(article.journal):
        return reject("Zenodo is disabled for this journal")

    if not identifiers:
        if default_doi_provider(article.journal) not in (
            "zenodo", "manual"
        ):
            return reject(
                "Journal DOI provider is not Zenodo or Manual"
            )

        return ProductionEligibility(
            True,
            "Eligible for new DOI reservation",
            mode="reserve_new",
        )

    if len(identifiers) != 1:
        return reject(
            "Multiple DOI identifiers require manual review"
        )

    if not zenodo_archive_enabled(article.journal):
        return reject(
            "Archiving articles with existing DOI is disabled"
        )

    identifier = identifiers[0]
    doi = identifier.identifier

    if identifier.doi_provider == "zenodo":
        return reject("Article already has a Zenodo DOI")

    if not identifier.enabled:
        return reject("Existing DOI is disabled")

    if not DOI_PATTERN.fullmatch(doi):
        return reject("Existing DOI format is invalid")

    status = CrossrefStatus.objects.filter(
        identifier=identifier,
    ).first()

    accepted = {
        CrossrefStatus.REGISTERED,
        CrossrefStatus.REGISTERED_BUT_CITATION_PROBLEMS,
    }

    if not status or status.message not in accepted:
        return reject(
            "Crossref registration is not locally confirmed"
        )

    return ProductionEligibility(
        True,
        "Existing DOI locally confirmed; external review required",
        doi=doi,
        mode="existing_doi",
    )


def build_production_metadata(
    article, *, check_existing=True
):

    result = check_production_eligibility(
        article,
        check_existing=check_existing,
    )

    if not result.eligible:
        raise ProductionMetadataError(result.reason)

    title = normalize_text(article.title)
    abstract = normalize_text(article.abstract)

    if not title or not abstract:
        raise ProductionMetadataError(
            "Title or abstract is missing"
        )

    creators = [
        map_author(author)
        for author in article.frozenauthor_set.all()
    ]

    license_id = resolve_zenodo_license(
        article.license
    )

    metadata = journal_article_metadata(
        title=title,
        creators=creators,
        description=abstract,
        license_id=license_id,
        publication_date=article.date_published.date(),
    )

    if result.mode == "existing_doi":

        metadata.pop("prereserve_doi", None)
        metadata["doi"] = result.doi

    else:

        metadata.pop("doi", None)
        metadata["prereserve_doi"] = True

    return metadata


@transaction.atomic
def prepare_production_deposit(
    article_id, *, confirmed=False
):

    if not getattr(
        settings,
        "ZENODO_PRODUCTION_WRITE_ENABLED",
        False,
    ):
        raise ProductionMetadataError(
            "Production operations are disabled"
        )

    if confirmed is not True:
        raise ProductionMetadataError(
            "Explicit confirmation is required"
        )

    article = Article.objects.select_for_update().get(
        pk=article_id
    )

    from identifiers.zenodo_production_permissions import (
        is_production_article_allowed,
    )

    if not is_production_article_allowed(article):
        raise ProductionMetadataError(
            "Article is not approved for Production"
        )

    metadata = build_production_metadata(article)

    # Validate actual PDF before preparing the deposit.
    with open_public_article_pdf(article):
        pass

    return ZenodoDeposit.objects.create(
        article=article,
        is_sandbox=False,
        status=ZenodoDeposit.Status.READY,
        metadata_snapshot=metadata,
    )
