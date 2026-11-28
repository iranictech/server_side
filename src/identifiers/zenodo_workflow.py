"""
Zenodo Sandbox deposit workflow.

Phase 1: reserve one local operation before contacting Zenodo.

No HTTP requests, PDF uploads, or DOI registration.
"""

from django.db import transaction
from identifiers.zenodo_sandbox import Draft, ZenodoError, _sandbox_url
from urllib.parse import urlparse
import re

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

    READY means no remote creation request has been initiated.
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
            status=ZenodoDeposit.Status.READY,
            metadata_snapshot=metadata,
        )

        return deposit


def claim_sandbox_draft_creation(deposit_id):
    """
    Atomically claim one READY sandbox deposit.

    No network requests. No automatic retries.
    A stale CREATING record requires reconciliation.
    """
    if type(deposit_id) is not int or deposit_id <= 0:
        raise ZenodoWorkflowError("Invalid deposit ID")

    updated = (
        ZenodoDeposit.objects.filter(
            pk=deposit_id,
            is_sandbox=True,
            status=ZenodoDeposit.Status.READY,
            deposition_id__isnull=True,
        )
        .update(status=ZenodoDeposit.Status.CREATING)
    )

    if updated != 1:
        raise ZenodoWorkflowError(
            "Deposit is not READY or cannot be claimed"
        )

    return ZenodoDeposit.objects.get(pk=deposit_id)


def create_sandbox_remote_draft(deposit_id, client):
    """
    Claim a READY deposit and create exactly one remote draft attempt.

    The HTTP request occurs outside the database transaction.
    CREATING and UNKNOWN records must never be retried automatically.

    A crash between remote creation and local persistence requires
    manual reconciliation.
    """

    deposit = claim_sandbox_draft_creation(deposit_id)

    try:
        draft = client.create_draft(deposit.metadata_snapshot)

        if not isinstance(draft, Draft):
            raise ZenodoError("Unexpected draft result")

        if (
            type(draft.deposition_id) is not int
            or draft.deposition_id <= 0
        ):
            raise ZenodoError("Invalid remote deposition ID")

        if (
            not isinstance(draft.reserved_doi, str)
            or len(draft.reserved_doi) > 300
            or not re.fullmatch(
                r"10\.\d{4,9}/[^\s]+",
                draft.reserved_doi,
            )
        ):
            raise ZenodoError("Invalid reserved DOI")

        _sandbox_url(draft.bucket_url)

        if not isinstance(draft.html_url, str):
            raise ZenodoError("Invalid draft URL")

        parsed = urlparse(draft.html_url)

        if (
            parsed.scheme != "https"
            or parsed.hostname != "sandbox.zenodo.org"
            or parsed.port is not None
            or parsed.username is not None
            or parsed.password is not None
            or not parsed.path.startswith("/deposit/")
            or parsed.query
            or parsed.fragment
            or len(draft.html_url) > 500
        ):
            raise ZenodoError("Invalid draft URL")

    except ZenodoError:
        ZenodoDeposit.objects.filter(
            pk=deposit_id,
            is_sandbox=True,
            status=ZenodoDeposit.Status.CREATING,
            deposition_id__isnull=True,
        ).update(
            status=ZenodoDeposit.Status.UNKNOWN,
            last_error="Remote draft creation outcome is unverified",
        )
        raise ZenodoWorkflowError(
            "Remote result is uncertain; automatic retry is prohibited"
        ) from None

    updated = ZenodoDeposit.objects.filter(
        pk=deposit_id,
        is_sandbox=True,
        status=ZenodoDeposit.Status.CREATING,
        deposition_id__isnull=True,
    ).update(
        deposition_id=draft.deposition_id,
        reserved_doi=draft.reserved_doi,
        record_url=draft.html_url,
        status=ZenodoDeposit.Status.DRAFT,
        last_error="",
    )

    if updated != 1:
        raise ZenodoWorkflowError(
            "Remote draft created but local persistence failed; "
            "manual reconciliation required"
        )

    return ZenodoDeposit.objects.get(pk=deposit_id)


def claim_sandbox_pdf_upload(
    deposit_id, *, filename, size, checksum
):
    """
    Atomically claim a PDF upload and persist its fingerprint.

    No HTTP requests. No automatic retries.
    """
    import re

    if type(deposit_id) is not int or deposit_id <= 0:
        raise ZenodoWorkflowError("Invalid deposit ID")

    if (
        not isinstance(filename, str)
        or not filename
        or len(filename) > 255
        or filename in (".", "..")
        or "/" in filename
        or "\\" in filename
        or not filename.lower().endswith(".pdf")
    ):
        raise ZenodoWorkflowError("Invalid PDF filename")

    if type(size) is not int or size <= 0:
        raise ZenodoWorkflowError("Invalid PDF size")

    if (
        not isinstance(checksum, str)
        or re.fullmatch(r"[0-9a-f]{32}", checksum) is None
    ):
        raise ZenodoWorkflowError("Invalid PDF checksum")

    updated = (
        ZenodoDeposit.objects.filter(
            pk=deposit_id,
            is_sandbox=True,
            status=ZenodoDeposit.Status.DRAFT,
            deposition_id__isnull=False,
            upload_filename="",
            upload_size__isnull=True,
            upload_checksum="",
        )
        .exclude(reserved_doi="")
        .update(
            status=ZenodoDeposit.Status.UPLOADING,
            upload_filename=filename,
            upload_size=size,
            upload_checksum=checksum,
        )
    )

    if updated != 1:
        raise ZenodoWorkflowError(
            "Deposit is not eligible for PDF upload "
            "or has already been claimed"
        )

    return ZenodoDeposit.objects.get(pk=deposit_id)
