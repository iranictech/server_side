"""
Validate a known Zenodo Sandbox draft before PDF upload.

Pure validation: no database writes and no HTTP requests.
"""

from identifiers.zenodo_sandbox import (
    Draft,
    ZenodoError,
    _sandbox_url,
)


class ZenodoUploadValidationError(RuntimeError):
    pass


def validate_sandbox_remote_draft(deposit, remote):
    if not deposit.is_sandbox:
        raise ZenodoUploadValidationError(
            "Production deposits are not supported"
        )

    remote_id = deposit.deposition_id

    if type(remote_id) is not int or remote_id <= 0:
        raise ZenodoUploadValidationError(
            "Invalid local deposition ID"
        )

    if not isinstance(deposit.reserved_doi, str) or not deposit.reserved_doi:
        raise ZenodoUploadValidationError(
            "Missing reserved DOI"
        )

    if not isinstance(remote, dict):
        raise ZenodoUploadValidationError(
            "Invalid remote response"
        )

    if type(remote.get("id")) is not int or remote["id"] != remote_id:
        raise ZenodoUploadValidationError(
            "Remote deposition identity mismatch"
        )

    if remote.get("submitted") is not False:
        raise ZenodoUploadValidationError(
            "Remote draft is not confirmed unpublished"
        )

    metadata = remote.get("metadata")
    if not isinstance(metadata, dict):
        raise ZenodoUploadValidationError(
            "Missing remote metadata"
        )

    reservation = metadata.get("prereserve_doi")
    if not isinstance(reservation, dict):
        raise ZenodoUploadValidationError(
            "Missing remote DOI reservation"
        )

    if reservation.get("doi") != deposit.reserved_doi:
        raise ZenodoUploadValidationError(
            "Reserved DOI mismatch"
        )

    links = remote.get("links")
    if not isinstance(links, dict):
        raise ZenodoUploadValidationError(
            "Missing remote links"
        )

    try:
        bucket = _sandbox_url(links.get("bucket"))
    except (ZenodoError, TypeError, ValueError):
        raise ZenodoUploadValidationError(
            "Invalid Sandbox bucket URL"
        ) from None

    html_url = links.get("html")
    expected_url = (
        "https://sandbox.zenodo.org/deposit/"
        + str(remote_id)
    )

    if (
        not isinstance(html_url, str)
        or html_url != expected_url
        or deposit.record_url != expected_url
    ):
        raise ZenodoUploadValidationError(
            "Remote draft URL mismatch"
        )

    return Draft(
        deposition_id=remote_id,
        reserved_doi=deposit.reserved_doi,
        bucket_url=bucket,
        html_url=html_url,
    )
