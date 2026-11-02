"""External researcher discovery using editor-approved public topics.

No manuscript title, abstract, or private keywords are read here.
No invitation or Janeway account is created.
"""

import os
import re

import requests


BASE_URL = "https://api.openalex.org"
AUTHOR_ID_RE = re.compile(r"(?:https://openalex\.org/)?(A[0-9]+)\Z")
WORK_ID_RE = re.compile(r"(?:https://openalex\.org/)?(W[0-9]+)\Z")


class OpenAlexDiscoveryError(RuntimeError):
    pass


def validate_public_topics(topics):
    if not isinstance(topics, (list, tuple)):
        raise ValueError("Topics must be a list.")

    if not 1 <= len(topics) <= 3:
        raise ValueError("Provide between 1 and 3 public topics.")

    cleaned = []
    seen = set()

    for topic in topics:
        if not isinstance(topic, str):
            raise ValueError("Each topic must be text.")

        topic = topic.strip()

        if not 2 <= len(topic) <= 80 or not topic.isprintable() or "@" in topic:
            raise ValueError("Invalid public topic.")

        key = topic.casefold()

        if key not in seen:
            seen.add(key)
            cleaned.append(topic)

    return cleaned


def propose_article_topics(article, *, max_topics=3):
    """Propose keywords locally; external disclosure still requires consent.

    These keywords are not automatically considered public.
    No manuscript title, abstract, or full text is accessed.
    """
    if type(max_topics) is not int or not 1 <= max_topics <= 3:
        raise ValueError("max_topics must be between 1 and 3.")

    topics = []
    seen = set()

    for keyword in article.keywords.all().order_by("pk"):
        try:
            topic = validate_public_topics([keyword.word])[0]
        except ValueError:
            continue

        normalized = topic.casefold()
        if normalized in seen:
            continue

        seen.add(normalized)
        topics.append(topic)

        if len(topics) >= max_topics:
            break

    return topics


def _extract_id(value, pattern):
    if not isinstance(value, str):
        return None

    match = pattern.fullmatch(value.strip())
    return match.group(1) if match else None


from .identity import extract_openalex_orcid


def discover_external_researchers(
    public_topics,
    *,
    limit=20,
    works_per_topic=5,
    api_key=None,
    session=None,
):
    """Find researchers from public OpenAlex works.

    public_topics MUST be approved for external disclosure.
    """

    topics = validate_public_topics(public_topics)

    if not isinstance(limit, int) or not 1 <= limit <= 30:
        raise ValueError("Invalid researcher limit.")

    if not isinstance(works_per_topic, int) or not 1 <= works_per_topic <= 10:
        raise ValueError("Invalid works limit.")

    key = api_key if api_key is not None else os.environ.get("OPENALEX_API_KEY", "")

    headers = {
        "User-Agent": "Janeway-ReviewerMatching/0.1",
        "Accept": "application/json",
    }

    if key:
        headers["Authorization"] = f"Bearer {key}"

    own_session = session is None

    if own_session:
        session = requests.Session()

    candidates = {}

    try:
        for topic in topics:
            try:
                response = session.get(
                    f"{BASE_URL}/works",
                    params={
                        "search": topic,
                        "per_page": works_per_topic,
                        "select": ("id,title,publication_year,authorships"),
                    },
                    headers=headers,
                    timeout=(3, 10),
                )

                response.raise_for_status()
                payload = response.json()

            except requests.RequestException as exc:
                raise OpenAlexDiscoveryError("OpenAlex request failed.") from exc

            except ValueError as exc:
                raise OpenAlexDiscoveryError("Invalid OpenAlex JSON response.") from exc

            works = payload.get("results")

            if not isinstance(works, list):
                raise OpenAlexDiscoveryError("Unexpected OpenAlex response structure.")

            for work in works:
                if not isinstance(work, dict):
                    continue

                work_id = _extract_id(
                    work.get("id"),
                    WORK_ID_RE,
                )

                if not work_id:
                    continue

                authorships = work.get("authorships") or []

                if not isinstance(authorships, list):
                    continue

                for authorship in authorships:
                    if not isinstance(authorship, dict):
                        continue

                    author = authorship.get("author") or {}

                    if not isinstance(author, dict):
                        continue

                    author_id = _extract_id(
                        author.get("id"),
                        AUTHOR_ID_RE,
                    )

                    name = author.get("display_name")

                    if not author_id or not isinstance(name, str) or not name.strip():
                        continue

                    record = candidates.setdefault(
                        author_id,
                        {
                            "openalex_id": author_id,
                            "name": name.strip(),
                            "source": "openalex",
                            "matched_public_topics": set(),
                            "evidence_work_ids": set(),
                            "orcid_candidates": set(),
                        },
                    )

                    resolved_orcid = extract_openalex_orcid(authorship)
                    if resolved_orcid:
                        record["orcid_candidates"].add(resolved_orcid)

                    record["matched_public_topics"].add(topic)
                    record["evidence_work_ids"].add(work_id)

    finally:
        if own_session:
            session.close()

    results = []

    for record in candidates.values():
        works = sorted(record["evidence_work_ids"])
        orcids = record["orcid_candidates"]

        if len(orcids) > 1:
            orcid = None
            orcid_status = "ambiguous"
        elif len(orcids) == 1:
            orcid = next(iter(orcids))
            orcid_status = "available"
        else:
            orcid = None
            orcid_status = "missing"

        results.append(
            {
                "openalex_id": record["openalex_id"],
                "name": record["name"],
                "orcid": orcid,
                "orcid_status": orcid_status,
                "source": "openalex",
                "matched_public_topics": sorted(record["matched_public_topics"]),
                "matching_works_count": len(works),
                "evidence_work_ids": works,
                "identity_verified": False,
                "coi_status": "not_checked",
                "invitation_ready": False,
                "semantic_score": None,
            }
        )

    results.sort(
        key=lambda item: (
            -item["matching_works_count"],
            item["openalex_id"],
        )
    )

    return results[:limit]
