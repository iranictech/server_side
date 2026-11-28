"""
Controlled PDF upload to a known Zenodo Sandbox draft.

No automatic retry. No publication.
"""

import hashlib

from identifiers.zenodo_models import ZenodoDeposit
from identifiers.zenodo_pdf import open_public_article_pdf
from identifiers.zenodo_workflow import (
    ZenodoWorkflowError,
    claim_sandbox_pdf_upload,
)
from identifiers.zenodo_upload_validation import (
    validate_sandbox_remote_draft,
)


def _pdf_fingerprint(stream):
    digest = hashlib.md5()
    size = 0

    while True:
        chunk = stream.read(1024 * 1024)
        if not chunk:
            break
        size += len(chunk)
        digest.update(chunk)

    stream.seek(0)

    if size == 0:
        raise ZenodoWorkflowError("Empty PDF")

    return size, digest.hexdigest()


def _remote_file_matches(remote, filename, size, checksum):
    files = remote.get("files")

    if not isinstance(files, list):
        return False

    matches = [
        item for item in files
        if isinstance(item, dict)
        and (item.get("filename") or item.get("key")) == filename
    ]

    if len(matches) != 1:
        return False

    item = matches[0]

    return (
        type(item.get("filesize")) is int
        and item["filesize"] == size
        and item.get("checksum") in (
            checksum,
            "md5:" + checksum,
        )
    )


def upload_sandbox_article_pdf(deposit_id, client):
    """
    Upload exactly one public article PDF attempt.

    A failed or uncertain remote operation requires reconciliation.
    """

    if type(deposit_id) is not int or deposit_id <= 0:
        raise ZenodoWorkflowError("Invalid deposit ID")

    deposit = ZenodoDeposit.objects.select_related(
        "article"
    ).get(pk=deposit_id)

    if (
        not deposit.is_sandbox
        or deposit.status != ZenodoDeposit.Status.DRAFT
        or type(deposit.deposition_id) is not int
        or deposit.deposition_id <= 0
        or not deposit.reserved_doi
    ):
        raise ZenodoWorkflowError(
            "Deposit is not eligible for upload"
        )

    # Validate the local PDF before claiming the remote operation.
    with open_public_article_pdf(deposit.article) as (
        stream,
        filename,
    ):
        size, checksum = _pdf_fingerprint(stream)

        # Atomic transition DRAFT -> UPLOADING.
        deposit = claim_sandbox_pdf_upload(
            deposit_id,
            filename=filename,
            size=size,
            checksum=checksum,
        )

        try:
            remote = client.get_deposition(
                deposit.deposition_id
            )

            draft = validate_sandbox_remote_draft(
                deposit,
                remote,
            )

            # Never overwrite a file already present remotely.
            files = remote.get("files")

            if not isinstance(files, list):
                raise ZenodoWorkflowError(
                    "Remote file inventory is unavailable"
                )

            if any(
                isinstance(item, dict)
                and (
                    item.get("filename") or item.get("key")
                ) == filename
                for item in files
            ):
                raise ZenodoWorkflowError(
                    "Remote filename already exists"
                )

            result = client.upload_pdf(
                draft,
                stream,
                filename,
            )

            if (
                not isinstance(result, dict)
                or result.get("key") != filename
            ):
                raise ZenodoWorkflowError(
                    "Upload response is unverified"
                )

            # Read back the remote inventory.
            verified = client.get_deposition(
                deposit.deposition_id
            )

            validate_sandbox_remote_draft(
                deposit,
                verified,
            )

            if not _remote_file_matches(
                verified,
                filename,
                size,
                checksum,
            ):
                raise ZenodoWorkflowError(
                    "Remote PDF verification failed"
                )

        except Exception:
            updated = ZenodoDeposit.objects.filter(
                pk=deposit_id,
                is_sandbox=True,
                status=ZenodoDeposit.Status.UPLOADING,
            ).update(
                status=ZenodoDeposit.Status.UNKNOWN,
                last_error=(
                    "PDF upload outcome requires reconciliation"
                ),
            )

            if updated != 1:
                raise ZenodoWorkflowError(
                    "Upload state changed; manual reconciliation required"
                ) from None

            raise ZenodoWorkflowError(
                "PDF upload not confirmed; "
                "automatic retry is prohibited"
            ) from None

        updated = ZenodoDeposit.objects.filter(
            pk=deposit_id,
            is_sandbox=True,
            status=ZenodoDeposit.Status.UPLOADING,
        ).update(
            status=ZenodoDeposit.Status.UPLOADED,
            last_error="",
        )

        if updated != 1:
            raise ZenodoWorkflowError(
                "Remote upload verified but local persistence failed; "
                "manual reconciliation required"
            )

    return ZenodoDeposit.objects.get(pk=deposit_id)
