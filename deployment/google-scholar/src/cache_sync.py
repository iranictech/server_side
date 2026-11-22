import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from collector import normalize
from fingerprint import identity_fingerprint
from verification import verify_candidate

JOURNAL_ID = int(os.environ["GOLD_SCHOLAR_JOURNAL_ID"])
JOURNAL_CODE = os.environ["GOLD_SCHOLAR_JOURNAL"]
BASE = Path(os.environ["GOLD_SCHOLAR_CACHE_DIR"])

if JOURNAL_ID <= 0 or not JOURNAL_CODE.strip():
    raise ValueError("Invalid journal configuration")

INPUT = BASE / f"input-journal-{JOURNAL_ID}.json"
CACHE = BASE / f"journal-{JOURNAL_ID}.json"
OBSERVATIONS = BASE / f"observations-journal-{JOURNAL_ID}.json"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write(path, data):
    fd, tmp = tempfile.mkstemp(
        prefix=".scholar-sync-",
        dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())

        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--collect", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--max-articles",
        type=int,
        default=5,
        help="Maximum collection attempts per execution"
    )

    args = parser.parse_args()

    if args.max_articles < 1:
        parser.error("--max-articles must be positive")

    collected = 0

    if args.apply == args.dry_run:
        parser.error("Choose exactly one of --dry-run or --apply")

    if args.collect and not args.apply:
        parser.error("--collect requires --apply")

    source = read_json(INPUT)

    if CACHE.exists():
        previous = read_json(CACHE)
    else:
        previous = {
            "journal_id": JOURNAL_ID,
            "journal_code": JOURNAL_CODE,
            "source": "google_scholar",
            "articles": {},
        }

    if (
        source.get("journal_id") != JOURNAL_ID
        or source.get("journal_code") != JOURNAL_CODE
        or previous.get("journal_id") != JOURNAL_ID
        or previous.get("source") != "google_scholar"
        or not isinstance(source.get("articles"), list)
        or not isinstance(previous.get("articles"), dict)
    ):
        raise ValueError("Invalid journal or cache schema")

    now = datetime.now(timezone.utc).isoformat()
    current = {}
    observations = {}
    seen = set()

    if args.collect:
        from collector_v2 import inspect_article

    def collection_priority(article):
        old = previous["articles"].get(
            str(article["id"]), {}
        )

        if old.get("identity_fingerprint") != identity_fingerprint(article):
            return "", article["id"]

        last_attempt = old.get("last_attempt_at") or ""

        return last_attempt, article["id"]

    ordered_articles = sorted(
        source["articles"],
        key=collection_priority
    )

    for article in ordered_articles:
        pk = article["id"]
        if type(pk) is not int or pk <= 0 or pk in seen:
            raise ValueError("Invalid or duplicate article ID")
        seen.add(pk)

        key = str(pk)
        title = normalize(article.get("title"))
        fingerprint = identity_fingerprint(article)
        old = previous["articles"].get(key, {})

        # Preserve verified records only for unchanged identities.
        if (
            old.get("status") == "verified"
            and old.get("normalized_title") == title
            and old.get("identity_fingerprint") == fingerprint
            and type(old.get("citations")) is int
            and old["citations"] >= 0
        ):
            current[key] = dict(old)
        elif (
            old.get("normalized_title") == title
            and old.get("identity_fingerprint") in (None, fingerprint)
            and old.get("status") in (
                "skipped", "unverified", "candidate", "error"
            )
        ):
            current[key] = dict(old)
        else:
            current[key] = {
                "status": "unverified",
                "normalized_title": title,
                "checked_at": now,
                "reason": "Awaiting verified Scholar match",
            }

        current[key]["identity_fingerprint"] = fingerprint

        if args.collect and collected < args.max_articles:
            result = inspect_article(article)

            if result.get("status") != "skipped":
                collected += 1
            observations[key] = result

            status = result.get("status")

            verified, verification_reason = verify_candidate(
                article, result
            )

            observations[key]["verification_reason"] = verification_reason

            if verified is not None:
                current[key] = verified

            elif status == "skipped":
                if current[key]["status"] != "verified":
                    current[key].update({
                        "status": "skipped",
                        "reason": result.get("reason"),
                        "checked_at": now,
                    })

            elif status in ("candidate", "unverified", "error"):
                if current[key]["status"] != "verified":
                    current[key].update({
                        "status": status,
                        "checked_at": now,
                        "reason": (
                            "Manual verification required"
                            if status == "candidate"
                            else "No verified match"
                            if status == "unverified"
                            else result.get("reason", "Collector error")
                        ),
                    })
            else:
                raise ValueError("Unexpected collector status")

        if key in observations:
            if observations[key].get("status") != "skipped":
                current[key]["last_attempt_at"] = now

        print(
            "Article:", pk,
            "| Cache:", current[key]["status"],
            "| Observation:",
            observations.get(key, {}).get("status", "not collected"),
            flush=True,
        )

    document = {
        "journal_id": JOURNAL_ID,
        "journal_code": JOURNAL_CODE,
        "source": "google_scholar",
        "updated_at": now,
        "articles": current,
    }

    print("Collection attempts:", collected)
    print("Collection limit:", args.max_articles)
    print("Entries:", len(current))
    print("Collect:", args.collect)
    print("Apply:", args.apply)

    if args.apply:
        if args.collect:
            atomic_write(OBSERVATIONS, {
                "journal_id": JOURNAL_ID,
                "source": "google_scholar",
                "checked_at": now,
                "articles": observations,
            })

        atomic_write(CACHE, document)
        print("CACHE UPDATED:", CACHE)
    else:
        print("DRY RUN: No files modified")


if __name__ == "__main__":
    main()
