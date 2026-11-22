import json
import re
import sys
import unicodedata
from difflib import SequenceMatcher
from itertools import islice
from pathlib import Path

from scholarly import scholarly

INPUT = Path(
    "/var/lib/janeway/gold-scholar/input-journal-12.json"
)

def normalize(value):
    value = unicodedata.normalize("NFKC", str(value or ""))
    value = re.split(
        r"\bAbstract\b", value, maxsplit=1, flags=re.I
    )[0]
    value = re.sub(r"[^\w\s-]", " ", value.lower())
    return " ".join(value.split())

def inspect_article(article):
    article_id = article["id"]
    title = normalize(article.get("title"))
    year = article.get("year")

    if (
        len(title) < 24
        or any(
            word in title
            for word in ("demo", "synthetic", "test")
        )
    ):
        return {
            "id": article_id,
            "status": "skipped",
            "reason": "Test or invalid article title",
        }

    matches = []

    try:
        results = scholarly.search_pubs(title)

        for result in islice(results, 5):
            bib = result.get("bib") or {}
            candidate_title = bib.get("title") or ""
            candidate_year = bib.get("pub_year") or bib.get("year")

            similarity = SequenceMatcher(
                None,
                title,
                normalize(candidate_title),
            ).ratio()

            if (
                similarity >= 0.96
                and (
                    not year
                    or (
                        candidate_year
                        and str(candidate_year) == str(year)
                    )
                )
            ):
                matches.append({
                    "scholar_title": candidate_title,
                    "scholar_year": candidate_year,
                    "citations": result.get("num_citations"),
                    "scholar_url": result.get("pub_url"),
                    "similarity": round(similarity, 4),
                })

    except Exception as exc:
        return {
            "id": article_id,
            "status": "error",
            "reason": type(exc).__name__,
        }

    return {
        "id": article_id,
        "status": (
            "candidate" if len(matches) == 1
            else "unverified"
        ),
        "matches": matches,
    }

def main():
    data = json.loads(INPUT.read_text(encoding="utf-8"))

    print("Journal:", data["journal_code"], flush=True)
    print("Source: Google Scholar", flush=True)
    print("Mode: READ ONLY", flush=True)

    for article in data["articles"]:
        result = inspect_article(article)
        print(
            json.dumps(result, ensure_ascii=False, indent=2),
            flush=True,
        )

if __name__ == "__main__":
    main()
