import re
import unicodedata

from collector import normalize


def normalize_name(value):
    value = unicodedata.normalize(
        "NFKD", str(value or "")
    )

    value = "".join(
        char for char in value
        if not unicodedata.combining(char)
    )

    value = re.sub(r"[^\w\s]", " ", value.casefold())

    return " ".join(value.split())


def normalize_doi(value):
    value = str(value or "").strip().lower()

    value = re.sub(
        r"^(https?://(dx\.)?doi\.org/|doi:\s*)",
        "",
        value
    )

    return value.rstrip("/") or None


def author_matches(expected, actual):
    actual = normalize_name(actual)

    full_name = normalize_name(
        expected.get("full_name")
    )

    if full_name and actual == full_name:
        return True

    if expected.get("is_corporate"):
        return False

    first = normalize_name(
        expected.get("first_name")
    )

    last = normalize_name(
        expected.get("last_name")
    )

    if not first or not last:
        return False

    expected_short = {
        f"{first} {last}",
        f"{first[0]} {last}",
        f"{last} {first}",
        f"{last} {first[0]}"
    }

    return actual in expected_short


def verify_identity(article, result):
    bib = result.get("bib") or {}

    expected_title = normalize(article.get("title"))
    actual_title = normalize(bib.get("title"))

    if not expected_title or expected_title != actual_title:
        return False, "title_mismatch"

    expected_year = article.get("year")
    actual_year = bib.get("pub_year") or bib.get("year")

    if not expected_year or str(expected_year) != str(actual_year):
        return False, "year_mismatch"

    expected_doi = normalize_doi(article.get("doi"))
    actual_doi = normalize_doi(
        bib.get("doi") or result.get("doi")
    )

    if expected_doi and actual_doi:
        if expected_doi != actual_doi:
            return False, "doi_mismatch"

    expected_authors = article.get("authors") or []
    actual_authors = bib.get("author") or []

    if isinstance(actual_authors, str):
        actual_authors = re.split(
            r"\s+and\s+|;",
            actual_authors
        )

    if not expected_authors or not actual_authors:
        return False, "author_information_missing"

    if len(expected_authors) != len(actual_authors):
        return False, "author_count_mismatch"

    for expected, actual in zip(
        expected_authors, actual_authors
    ):
        if not author_matches(expected, actual):
            return False, "author_mismatch"

    citations = result.get("num_citations")

    if type(citations) is not int or citations < 0:
        return False, "invalid_citation_count"

    return True, "identity_match"
