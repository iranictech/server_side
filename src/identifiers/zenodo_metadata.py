"""
Map published Janeway articles to Zenodo deposition metadata.

Read-only:
- no database writes
- no API requests
- no DOI registration
"""

import re
from html import unescape
from urllib.parse import urlparse

from django.utils.html import strip_tags

from identifiers.zenodo_sandbox import journal_article_metadata
from identifiers.zenodo_service import check_zenodo_eligibility


ORCID_PATTERN = re.compile(
    r"^\d{4}-\d{4}-\d{4}-[\dX]{4}$"
)


def is_valid_orcid(orcid):
    """Validate ORCID using the ISO 7064 MOD 11-2 checksum."""
    if not isinstance(orcid, str):
        return False

    if not ORCID_PATTERN.fullmatch(orcid):
        return False

    digits = orcid.replace("-", "")
    total = 0

    for digit in digits[:15]:
        total = (total + int(digit)) * 2

    remainder = total % 11
    check_digit = (12 - remainder) % 11
    expected = "X" if check_digit == 10 else str(check_digit)

    return digits[-1] == expected


class ZenodoMetadataError(ValueError):
    pass


def normalize_text(value):
    return " ".join(
        unescape(strip_tags(str(value or ""))).split()
    )


def resolve_zenodo_license(license_object):
    """
    Fail closed for unsupported or ambiguous licenses.

    Phase 1 supports Creative Commons Attribution 4.0 only.
    """
    if license_object is None:
        raise ZenodoMetadataError("Article license is missing")

    url = (license_object.url or "").strip()
    parsed = urlparse(url)

    if (
        parsed.scheme == "https"
        and parsed.hostname == "creativecommons.org"
        and parsed.port is None
        and parsed.username is None
        and parsed.password is None
        and parsed.path.rstrip("/") == "/licenses/by/4.0"
        and not parsed.query
        and not parsed.fragment
    ):
        return "cc-by-4.0"

    raise ZenodoMetadataError(
        "Article license is not supported by the current Zenodo mapper"
    )


def map_author(author):
    if author.is_corporate:
        name = normalize_text(author.corporate_name)
    else:
        name = normalize_text(author.dc_name_string)

    if not name:
        raise ZenodoMetadataError(
            "Author name is missing"
        )

    creator = {"name": name}

    if not author.is_corporate:
        affiliation = normalize_text(author.institution)

        if affiliation:
            creator["affiliation"] = affiliation

        orcid_uri = (author.orcid_uri or "").strip()

        if orcid_uri:
            prefix = "https://orcid.org/"

            if not orcid_uri.startswith(prefix):
                raise ZenodoMetadataError(
                    "Invalid ORCID URL"
                )

            orcid = orcid_uri[len(prefix):]

            if not is_valid_orcid(orcid):
                raise ZenodoMetadataError(
                    "Invalid ORCID format"
                )

            creator["orcid"] = orcid

    return creator


def build_zenodo_metadata(article):
    """
    Produce metadata for review before creating a remote draft.

    Eligibility is preliminary and must be rechecked under
    appropriate database locking before a remote operation.
    """
    result = check_zenodo_eligibility(
        article,
        is_sandbox=True,
    )

    if not result.eligible:
        raise ZenodoMetadataError(result.reason)

    title = normalize_text(article.title)
    abstract = normalize_text(article.abstract)

    if not title:
        raise ZenodoMetadataError(
            "Article title is missing"
        )

    if not abstract:
        raise ZenodoMetadataError(
            "Article abstract is missing"
        )

    creators = [
        map_author(author)
        for author in article.frozenauthor_set.all()
    ]

    if not creators:
        raise ZenodoMetadataError(
            "Article has no authors"
        )

    license_id = resolve_zenodo_license(
        article.license
    )

    return journal_article_metadata(
        title=title,
        creators=creators,
        description=abstract,
        license_id=license_id,
        publication_date=article.date_published.date(),
    )
