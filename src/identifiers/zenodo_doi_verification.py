"""
Read-only verification of existing Crossref DOI.

No DOI registration.
No metadata updates.
"""

import re
import unicodedata
from urllib.parse import quote

import requests

from identifiers.zenodo_metadata import normalize_text


class DOIVerificationError(RuntimeError):
    pass


DOI_PATTERN = re.compile(
    r"10\.\d{4,9}/[^\s]+"
)


def normalize_title(value):
    value = normalize_text(value)

    value = unicodedata.normalize(
        "NFKC", value
    ).casefold()

    return " ".join(value.split())


def verify_crossref_doi(
    doi,
    expected_title,
    *,
    session=None,
):
    if not isinstance(doi, str):
        raise DOIVerificationError(
            "Invalid DOI"
        )

    if not DOI_PATTERN.fullmatch(doi):
        raise DOIVerificationError(
            "Invalid DOI format"
        )

    title = normalize_title(expected_title)

    if not title:
        raise DOIVerificationError(
            "Expected article title is missing"
        )

    session = session or requests

    url = (
        "https://api.crossref.org/works/"
        + quote(doi, safe="")
    )

    try:
        response = session.get(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent":
                    "Janeway-Zenodo-Verification/1.0",
            },
            timeout=20,
            allow_redirects=False,
        )

    except requests.RequestException:
        raise DOIVerificationError(
            "Crossref API connection failed"
        ) from None

    if response.status_code != 200:
        raise DOIVerificationError(
            "Crossref registration could not be verified"
        )

    try:
        payload = response.json()
        record = payload["message"]

        remote_doi = record["DOI"]
        remote_titles = record["title"]

    except (ValueError, TypeError, KeyError):
        raise DOIVerificationError(
            "Invalid Crossref API response"
        ) from None

    if (
        not isinstance(remote_doi, str)
        or remote_doi.casefold() != doi.casefold()
    ):
        raise DOIVerificationError(
            "Crossref DOI mismatch"
        )

    if not isinstance(remote_titles, list):
        raise DOIVerificationError(
            "Crossref title is unavailable"
        )

    titles = [
        normalize_title(item)
        for item in remote_titles
        if isinstance(item, str)
    ]

    if title not in titles:
        raise DOIVerificationError(
            "Crossref article title mismatch"
        )

    if record.get("type") != "journal-article":
        raise DOIVerificationError(
            "DOI is not registered as a journal article"
        )

    return {
        "verified": True,
        "doi": remote_doi,
        "provider": "crossref",
        "title_matched": True,
    }
