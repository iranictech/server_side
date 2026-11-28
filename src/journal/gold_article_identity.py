"""Article identity fingerprint for Gold citation validation."""

import json

import hashlib

import re

import unicodedata

def normalize(value):
    value = unicodedata.normalize("NFKC", str(value or ""))
    value = re.split(
        r"\bAbstract\b", value, maxsplit=1, flags=re.I
    )[0]
    value = re.sub(r"[^\w\s-]", " ", value.lower())
    return " ".join(value.split())

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
