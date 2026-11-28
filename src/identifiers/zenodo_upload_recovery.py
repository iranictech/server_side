"""
Read-only verification of uncertain Zenodo Sandbox PDF uploads.

No PUT, POST, retry, publication, or database writes.
"""

import re

from identifiers.zenodo_models import ZenodoDeposit
from identifiers.zenodo_sandbox import ZenodoError
from identifiers.zenodo_upload_validation import (
    ZenodoUploadValidationError,
    validate_sandbox_remote_draft,
)
from identifiers.zenodo_upload_workflow import (
    _remote_file_matches,
)


class ZenodoUploadRecoveryError(RuntimeError):
    pass


def inspect_sandbox_pdf_upload(deposit_id, client):
    """
    Compare the persisted upload fingerprint with remote files.

    Outcome:
        verified   - exactly one remote file matches
        mismatch   - the named file exists but differs
        unresolved - remote state cannot be confirmed

    Never modifies local state.
    """

    if type(deposit_id) is not int or deposit_id <= 0:
        raise ZenodoUploadRecoveryError(
            "Invalid local deposit ID"
        )

    deposit = ZenodoDeposit.objects.get(pk=deposit_id)

    if not deposit.is_sandbox:
        raise ZenodoUploadRecoveryError(
            "Production deposits are not supported"
        )

    if deposit.status not in (
        ZenodoDeposit.Status.UNKNOWN,
        ZenodoDeposit.Status.UPLOADING,
    ):
        raise ZenodoUploadRecoveryError(
            "Deposit is not in an uncertain upload state"
        )

    if (
        type(deposit.deposition_id) is not int
        or deposit.deposition_id <= 0
    ):
        raise ZenodoUploadRecoveryError(
            "Remote deposition ID is unknown"
        )

    filename = deposit.upload_filename
    size = deposit.upload_size
    checksum = deposit.upload_checksum

    if (
        not isinstance(filename, str)
        or not filename
        or len(filename) > 255
        or "/" in filename
        or "\\" in filename
        or not filename.lower().endswith(".pdf")
        or type(size) is not int
        or size <= 0
        or not isinstance(checksum, str)
        or re.fullmatch(r"[0-9a-f]{32}", checksum) is None
    ):
        raise ZenodoUploadRecoveryError(
            "Persisted PDF fingerprint is missing or invalid"
        )

    result = {
        "local_deposit_id": deposit.pk,
        "remote_deposition_id": deposit.deposition_id,
        "local_status": deposit.status,
        "outcome": "unresolved",
        "reason": "remote_not_verified",
    }

    try:
        remote = client.get_deposition(
            deposit.deposition_id
        )

        validate_sandbox_remote_draft(
            deposit, remote
        )

    except (ZenodoError, ZenodoUploadValidationError):
        result["reason"] = "remote_validation_failed"
        return result

    files = remote.get("files")

    if not isinstance(files, list):
        result["reason"] = "file_inventory_unavailable"
        return result

    matching_names = [
        item for item in files
        if isinstance(item, dict)
        and (
            item.get("filename") or item.get("key")
        ) == filename
    ]

    if not matching_names:
        result["reason"] = "expected_file_not_found"
        return result

    if len(matching_names) != 1:
        result["reason"] = "ambiguous_remote_files"
        return result

    if _remote_file_matches(
        remote, filename, size, checksum
    ):
        result["outcome"] = "verified"
        result["reason"] = "fingerprint_matched"
    else:
        item = matching_names[0]

        if (
            type(item.get("filesize")) is not int
            or not isinstance(item.get("checksum"), str)
        ):
            result["reason"] = "remote_fingerprint_incomplete"
        else:
            result["outcome"] = "mismatch"
            result["reason"] = "fingerprint_mismatch"

    return result
