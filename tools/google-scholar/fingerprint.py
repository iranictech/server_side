import json
import hashlib

from collector import normalize
from identity import normalize_name, normalize_doi


def identity_fingerprint(article):
    authors = []

    for author in article.get("authors") or []:
        authors.append({
            "first_name": normalize_name(
                author.get("first_name")
            ),
            "middle_name": normalize_name(
                author.get("middle_name")
            ),
            "last_name": normalize_name(
                author.get("last_name")
            ),
            "full_name": normalize_name(
                author.get("full_name")
            ),
            "is_corporate": bool(
                author.get("is_corporate")
            )
        })

    identity = {
        "title": normalize(article.get("title")),
        "year": str(article.get("year") or ""),
        "doi": normalize_doi(article.get("doi")),
        "authors": authors
    }

    payload = json.dumps(
        identity,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":")
    )

    return hashlib.sha256(
        payload.encode("utf-8")
    ).hexdigest()
