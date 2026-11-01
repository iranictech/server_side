"""Researcher identity checks for external reviewer discovery.

ORCID comparisons are conservative. No identity match is inferred
from a person's name alone.
"""

import re

from core.models import Account
from submission.models import FrozenAuthor


ORCID_RE = re.compile(
    r"(?:(?:https?://)?(?:www\.)?orcid\.org/)?"
    r"([0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{3}[0-9X])/?",
    re.IGNORECASE,
)


def normalize_orcid(value):
    """Normalize an ORCID URL or identifier; format check only."""
    if not isinstance(value, str):
        return ""

    match = ORCID_RE.fullmatch(value.strip())
    return match.group(1).upper() if match else ""


def extract_openalex_orcid(record):
    """Read the resolved OpenAlex author's primary ORCID.

    Accept an authorship object or an author profile object.
    Do not infer identity from the raw authorship name.
    """
    if not isinstance(record, dict):
        return ""

    author = record.get("author", record)

    if not isinstance(author, dict):
        return ""

    return normalize_orcid(author.get("orcid"))


def resolve_janeway_orcid(article, value):
    """Classify an ORCID without exposing account details.

    Returns:
        no_valid_orcid
        article_author
        existing_janeway_account
        new_external
    """
    identifier = normalize_orcid(value)

    if not identifier:
        return "no_valid_orcid"

    frozen_orcids = FrozenAuthor.objects.filter(
        article=article,
    ).values_list("frozen_orcid", flat=True)

    if any(
        normalize_orcid(item) == identifier
        for item in frozen_orcids
    ):
        return "article_author"

    linked_author_orcids = article.author_accounts.values_list(
        "orcid", flat=True
    )

    if any(
        normalize_orcid(item) == identifier
        for item in linked_author_orcids
    ):
        return "article_author"

    # The substring filter narrows the candidates. Exact canonical
    # comparison prevents treating partial matches as identical.
    existing_orcids = Account.objects.filter(
        orcid__icontains=identifier
    ).values_list("orcid", flat=True)

    if any(
        normalize_orcid(item) == identifier
        for item in existing_orcids
    ):
        return "existing_janeway_account"

    return "new_external"
