"""
Controlled reconciliation of a verified Zenodo Sandbox PDF.

No PUT, POST, retry, or publication.
Database mutation requires explicit confirmation.
"""

from identifiers.zenodo_models import ZenodoDeposit
from identifiers.zenodo_upload_recovery import (
    inspect_sandbox_pdf_upload,
)


class ZenodoUploadReconcileError(RuntimeError):
    pass


def reconcile_sandbox_pdf_upload(
    deposit_id,
    client,
    *,
    confirmed=False,
):
    """
    Verify a remote PDF before conditionally updating local state.

    Only UNKNOWN -> UPLOADED is supported.

    UPLOADING is intentionally excluded because another worker
    may still be processing the upload.
    """

    if type(deposit_id) is not int or deposit_id <= 0:
        raise ZenodoUploadReconcileError(
            "Invalid deposit ID"
        )

    if type(confirmed) is not bool:
        raise ZenodoUploadReconcileError(
            "Confirmation must be boolean"
        )

    deposit = ZenodoDeposit.objects.get(pk=deposit_id)

    if (
        not deposit.is_sandbox
        or deposit.status != ZenodoDeposit.Status.UNKNOWN
    ):
        raise ZenodoUploadReconcileError(
            "Only uncertain Sandbox deposits can be reconciled"
        )

    # Capture the state that must remain unchanged.
    snapshot = {
        "pk": deposit.pk,
        "is_sandbox": True,
        "status": ZenodoDeposit.Status.UNKNOWN,
        "deposition_id": deposit.deposition_id,
        "reserved_doi": deposit.reserved_doi,
        "record_url": deposit.record_url,
        "upload_filename": deposit.upload_filename,
        "upload_size": deposit.upload_size,
        "upload_checksum": deposit.upload_checksum,
    }

    verification = inspect_sandbox_pdf_upload(
        deposit_id,
        client,
    )

    if verification["outcome"] != "verified":
        return {
            "changed": False,
            "outcome": verification["outcome"],
            "reason": verification["reason"],
        }

    if not confirmed:
        return {
            "changed": False,
            "outcome": "verified",
            "reason": "confirmation_required",
        }

    # Conditional update protects against concurrent local changes.
    updated = ZenodoDeposit.objects.filter(
        **snapshot
    ).update(
        status=ZenodoDeposit.Status.UPLOADED,
        last_error="",
    )

    if updated != 1:
        raise ZenodoUploadReconcileError(
            "Local deposit changed during verification; "
            "manual review required"
        )

    return {
        "changed": True,
        "outcome": "verified",
        "reason": "reconciled",
    }
