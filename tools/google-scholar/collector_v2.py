from itertools import islice

from scholarly import scholarly
from collector import normalize
from identity import verify_identity


def inspect_article(article, search=None):
    article_id = article["id"]
    title = normalize(article.get("title"))

    if (
        len(title) < 24
        or title.startswith(("demo ", "test ", "synthetic "))
    ):
        return {
            "id": article_id,
            "status": "skipped",
            "reason": "Test or invalid article title"
        }

    if search is None:
        search = scholarly.search_pubs

    matches = []
    rejected = []

    try:
        for item in islice(search(title), 5):
            valid, reason = verify_identity(article, item)
            bib = item.get("bib") or {}

            if valid:
                matches.append({
                    "scholar_title": bib.get("title"),
                    "scholar_year": (
                        bib.get("pub_year") or bib.get("year")
                    ),
                    "scholar_authors": bib.get("author"),
                    "scholar_doi": (
                        bib.get("doi") or item.get("doi")
                    ),
                    "citations": item.get("num_citations"),
                    "scholar_url": item.get("pub_url"),
                    "scholar_pub_id": item.get("author_pub_id"),
                    "normalized_title": title
                })
            else:
                rejected.append({
                    "title": bib.get("title"),
                    "reason": reason
                })

    except Exception as exc:
        return {
            "id": article_id,
            "status": "error",
            "reason": type(exc).__name__
        }

    if len(matches) == 1:
        return {
            "id": article_id,
            "status": "candidate",
            "reason": "Identity checks passed",
            "matches": matches,
            "rejected": rejected
        }

    return {
        "id": article_id,
        "status": "unverified",
        "reason": (
            "Ambiguous matches"
            if len(matches) > 1
            else "No verified identity match"
        ),
        "matches": matches,
        "rejected": rejected
    }
