"""Conservative local ORCID evidence for editorial COI screening.

Only already-stored manuscript author identifiers are read here.
No manuscript identifiers are disclosed to OpenAlex; no COI is cleared.
"""

from submission.models import FrozenAuthor

from .identity import normalize_orcid


def get_article_author_orcids(article):
    """Collect canonical ORCIDs for manuscript authors, without names."""
    frozen_orcids = FrozenAuthor.objects.filter(article=article).values_list(
        "frozen_orcid", flat=True
    )
    linked_orcids = article.author_accounts.values_list("orcid", flat=True)
    return {
        normalized
        for raw in (*frozen_orcids, *linked_orcids)
        if (normalized := normalize_orcid(raw))
    }
