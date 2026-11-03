"""Conservative local COI evidence from sampled OpenAlex works.

No complete conflict review or reviewer eligibility decision is implied.
"""

import re

from submission.models import FrozenAuthor

from .identity import normalize_orcid


WORK_ID_RE = re.compile(r"W[0-9]+\Z")


def get_article_author_orcids(article):
    """Collect manuscript-author ORCIDs locally, without external requests."""
    frozen_orcids = FrozenAuthor.objects.filter(article=article).values_list(
        "frozen_orcid", flat=True
    )
    linked_orcids = article.author_accounts.values_list("orcid", flat=True)
    return {
        normalized
        for value in (*frozen_orcids, *linked_orcids)
        if (normalized := normalize_orcid(value))
    }


def sampled_coauthorship_evidence(coauthor_work_ids, author_orcids):
    """Return validated sampled work IDs coauthored with manuscript authors."""
    if not isinstance(coauthor_work_ids, dict):
        return []

    matches = set()
    for raw_orcid, work_ids in coauthor_work_ids.items():
        if normalize_orcid(raw_orcid) not in author_orcids:
            continue
        if not isinstance(work_ids, (list, tuple)):
            continue
        for work_id in work_ids:
            if isinstance(work_id, str) and WORK_ID_RE.fullmatch(work_id):
                matches.add(work_id)
    return sorted(matches)
