import json
import os
import tempfile
from pathlib import Path
from datetime import datetime, timezone

from journal.models import Journal
from submission.models import Article, STAGE_PUBLISHED

CACHE_DIR = Path(os.environ["GOLD_SCHOLAR_CACHE_DIR"])
JOURNAL_CODE = os.environ["GOLD_SCHOLAR_JOURNAL"]
JOURNAL_ID = int(os.environ["GOLD_SCHOLAR_JOURNAL_ID"])

if JOURNAL_ID <= 0 or not JOURNAL_CODE.strip():
    raise ValueError("Invalid journal configuration")

journal = Journal.objects.get(
    code=JOURNAL_CODE, pk=JOURNAL_ID
)

articles = Article.objects.filter(
    journal=journal,
    stage=STAGE_PUBLISHED
).order_by("-date_published", "-pk")

data = {
    "journal_id": journal.pk,
    "journal_code": journal.code,
    "exported_at": datetime.now(timezone.utc).isoformat(),
    "articles": []
}

for article in articles:
    authors = []

    for author in article.frozen_authors().order_by("order", "pk"):
        authors.append({
            "first_name": author.first_name or "",
            "middle_name": author.middle_name or "",
            "last_name": author.last_name or "",
            "full_name": author.full_name(),
            "is_corporate": author.is_corporate
        })

    doi = article.get_doi()

    data["articles"].append({
        "id": article.pk,
        "title": str(article.title or ""),
        "year": (
            article.date_published.year
            if article.date_published else None
        ),
        "doi": str(doi) if doi else None,
        "authors": authors
    })

output = CACHE_DIR / f"input-journal-{journal.pk}.json"

fd, tmp = tempfile.mkstemp(
    prefix=".scholar-export-",
    dir=str(CACHE_DIR)
)

try:
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())

    os.chmod(tmp, 0o644)
    os.replace(tmp, output)

finally:
    if os.path.exists(tmp):
        os.unlink(tmp)

print("JOURNAL:", journal.code)
print("EXPORTED ARTICLES:", len(data["articles"]))
print("OUTPUT:", output)

for item in data["articles"]:
    print(
        "Article:", item["id"],
        "| Authors:", len(item["authors"]),
        "| DOI:", item["doi"]
    )
