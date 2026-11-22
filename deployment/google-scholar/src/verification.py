from datetime import datetime, timezone

from fingerprint import identity_fingerprint
from identity import (
    normalize_name,
    normalize_doi,
    verify_identity,
)


def verify_candidate(article, observation):
    if observation.get("id") != article.get("id"):
        return None, "article_id_mismatch"

    if observation.get("status") != "candidate":
        return None, "not_a_candidate"

    matches = observation.get("matches") or []

    if len(matches) != 1:
        return None, "ambiguous_match"

    match = matches[0]

    result = {
        "bib": {
            "title": match.get("scholar_title"),
            "pub_year": match.get("scholar_year"),
            "author": match.get("scholar_authors"),
            "doi": match.get("scholar_doi"),
        },
        "num_citations": match.get("citations")
    }

    valid, reason = verify_identity(article, result)

    if not valid:
        return None, reason

    expected_authors = [
        normalize_name(a.get("full_name"))
        for a in article.get("authors", [])
    ]

    actual_authors = match.get("scholar_authors") or []

    if not isinstance(actual_authors, list):
        return None, "manual_author_review_required"

    actual_authors = [
        normalize_name(a) for a in actual_authors
    ]

    if expected_authors != actual_authors:
        return None, "manual_author_review_required"

    expected_doi = normalize_doi(article.get("doi"))
    actual_doi = normalize_doi(match.get("scholar_doi"))

    confidence = (
        "high"
        if expected_doi and expected_doi == actual_doi
        else "standard"
    )

    now = datetime.now(timezone.utc).isoformat()

    return {
        "status": "verified",
        "source": "google_scholar",
        "citations": match["citations"],
        "normalized_title": match["normalized_title"],
        "identity_fingerprint": identity_fingerprint(article),
        "scholar_title": match.get("scholar_title"),
        "scholar_authors": match.get("scholar_authors"),
        "scholar_year": match.get("scholar_year"),
        "scholar_doi": match.get("scholar_doi"),
        "scholar_url": match.get("scholar_url"),
        "scholar_pub_id": match.get("scholar_pub_id"),
        "confidence": confidence,
        "checked_at": now,
        "verified_at": now
    }, "verified"
