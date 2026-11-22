"""
Zenodo Sandbox deposit workflow.

Phase 1: reserve one local operation before contacting Zenodo.

No HTTP requests, PDF uploads, or DOI registration.
"""

from django.db import transaction

from identifiers.zenodo_metadata import build_zenodo_metadata
from identifiers.zenodo_models import ZenodoDeposit
from identifiers.zenodo_service import check_zenodo_eligibility
from submission.models import Article


class ZenodoWorkflowError(RuntimeError):
    pass


def begin_sandbox_deposit(article_id):
    """
    Create a durable local record for one Sandbox operation.

    Must not be called automatically from article.save()
    or publication signals.

    UNKNOWN means remote outcome is not yet established.
    Never retry remote creation solely because status is UNKNOWN.
    """

    with transaction.atomic():

        article = (
            Article.objects
            .select_for_update()
            .get(pk=article_id)
        )

        result = check_zenodo_eligibility(
            article,
            is_sandbox=True,
        )

        if not result.eligible:
            raise ZenodoWorkflowError(result.reason)

        metadata = build_zenodo_metadata(article)

        deposit = ZenodoDeposit.objects.create(
            article=article,
            is_sandbox=True,
            status=ZenodoDeposit.Status.UNKNOWN,
            metadata_snapshot=metadata,
        )

        return deposit
