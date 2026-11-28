"""
Controlled Zenodo Production workflow.

No automatic retries.
No publication.
Sandbox deposits are never accepted.
"""

from django.conf import settings

from identifiers.zenodo_doi_verification import (
    verify_crossref_doi,
    DOIVerificationError,
)

from identifiers.zenodo_production_metadata import (
    build_production_metadata,
)
from identifiers.zenodo_production_permissions import (
    is_production_article_allowed,
)

from identifiers.zenodo_models import ZenodoDeposit
from identifiers.zenodo_sandbox import Draft
from identifiers.zenodo_production import (
    ZenodoProductionClient,
    _production_url,
)
from identifiers.zenodo_pdf import open_public_article_pdf
from identifiers.zenodo_upload_workflow import (
    _pdf_fingerprint,
    _remote_file_matches,
)


class ProductionWorkflowError(RuntimeError):
    pass


def _guard(deposit, client, confirmed):
    if not getattr(
        settings, "ZENODO_PRODUCTION_WRITE_ENABLED", False
    ):
        raise ProductionWorkflowError(
            "Production operations are disabled"
        )

    if confirmed is not True:
        raise ProductionWorkflowError(
            "Explicit confirmation is required"
        )

    if deposit.is_sandbox:
        raise ProductionWorkflowError(
            "Sandbox deposit is not allowed"
        )

    if not is_production_article_allowed(deposit.article):
        raise ProductionWorkflowError(
            "Article is not approved for Production"
        )

    if deposit.article_id == 40:
        raise ProductionWorkflowError(
            "Demo article is excluded from Production"
        )

    if not isinstance(client, ZenodoProductionClient):
        raise ProductionWorkflowError(
            "Production client is required"
        )


def _transition(deposit, expected, **values):
    changed = ZenodoDeposit.objects.filter(
        pk=deposit.pk,
        is_sandbox=False,
        status=expected,
    ).update(**values)

    if changed != 1:
        raise ProductionWorkflowError(
            "Concurrent state change detected"
        )

    deposit.refresh_from_db()


def create_production_draft(
    deposit_id, client, *, confirmed=False
):
    deposit = ZenodoDeposit.objects.get(pk=deposit_id)

    _guard(deposit, client, confirmed)

    if (
        deposit.status != ZenodoDeposit.Status.READY
        or deposit.deposition_id is not None
    ):
        raise ProductionWorkflowError(
            "Deposit is not ready"
        )

    current_metadata = build_production_metadata(
        deposit.article,
        check_existing=False,
    )

    if current_metadata != deposit.metadata_snapshot:
        raise ProductionWorkflowError(
            "Article metadata changed after preparation"
        )

    existing_doi = current_metadata.get("doi")

    if existing_doi:
        try:
            verification = verify_crossref_doi(
                existing_doi,
                current_metadata["title"],
            )

        except DOIVerificationError:
            raise ProductionWorkflowError(
                "Existing Crossref DOI could not be verified"
            ) from None

        if verification.get("verified") is not True:
            raise ProductionWorkflowError(
                "Existing DOI verification failed"
            )

        if not getattr(
            settings,
            "ZENODO_PRODUCTION_EXISTING_DOI_ENABLED",
            False,
        ):
            raise ProductionWorkflowError(
                "Existing DOI archival is disabled"
            )

    else:
        if not getattr(
            settings,
            "ZENODO_PRODUCTION_NEW_DOI_ENABLED",
            False,
        ):
            raise ProductionWorkflowError(
                "New DOI reservation is disabled"
            )

    # Recheck article data after external verification.
    deposit.article.refresh_from_db()

    refreshed_metadata = build_production_metadata(
        deposit.article,
        check_existing=False,
    )

    if refreshed_metadata != deposit.metadata_snapshot:
        raise ProductionWorkflowError(
            "Article metadata changed during verification"
        )

    _transition(
        deposit,
        ZenodoDeposit.Status.READY,
        status=ZenodoDeposit.Status.CREATING,
    )

    try:
        draft = client.create_draft(
            deposit.metadata_snapshot
        )

        if not isinstance(draft, Draft):
            raise ProductionWorkflowError(
                "Invalid draft response"
            )

        _production_url(draft.bucket_url)

        _transition(
            deposit,
            ZenodoDeposit.Status.CREATING,
            status=ZenodoDeposit.Status.DRAFT,
            deposition_id=draft.deposition_id,
            reserved_doi=draft.reserved_doi,
            record_url=draft.html_url,
            last_error="",
        )

    except Exception:
        _transition(
            deposit,
            ZenodoDeposit.Status.CREATING,
            status=ZenodoDeposit.Status.UNKNOWN,
            last_error="Draft creation requires review",
        )
        raise ProductionWorkflowError(
            "Draft creation is unverified; do not retry"
        ) from None

    return deposit


def validate_production_draft(deposit, remote):
    if deposit.is_sandbox:
        raise ProductionWorkflowError(
            "Invalid environment"
        )

    if (
        type(remote.get("id")) is not int
        or remote["id"] != deposit.deposition_id
        or remote.get("submitted") is not False
    ):
        raise ProductionWorkflowError(
            "Remote draft identity mismatch"
        )

    metadata = remote.get("metadata") or {}
    existing_doi = deposit.metadata_snapshot.get("doi")

    if existing_doi:
        remote_doi = metadata.get("doi")
    else:
        reservation = metadata.get("prereserve_doi") or {}
        remote_doi = reservation.get("doi")

    if (
        not remote_doi
        or remote_doi != deposit.reserved_doi
    ):
        raise ProductionWorkflowError(
            "Remote DOI mismatch"
        )

    links = remote.get("links") or {}

    expected_url = (
        "https://zenodo.org/deposit/"
        + str(deposit.deposition_id)
    )

    if (
        links.get("html") != expected_url
        or deposit.record_url != expected_url
    ):
        raise ProductionWorkflowError(
            "Production draft URL mismatch"
        )

    return Draft(
        deposition_id=deposit.deposition_id,
        reserved_doi=deposit.reserved_doi,
        bucket_url=_production_url(links.get("bucket")),
        html_url=expected_url,
    )


def upload_production_pdf(
    deposit_id, client, *, confirmed=False
):
    deposit = ZenodoDeposit.objects.select_related(
        "article"
    ).get(pk=deposit_id)

    _guard(deposit, client, confirmed)

    if deposit.status != ZenodoDeposit.Status.DRAFT:
        raise ProductionWorkflowError(
            "Deposit is not ready for upload"
        )

    if deposit.upload_filename or deposit.upload_checksum:
        raise ProductionWorkflowError(
            "Previous upload attempt exists"
        )

    with open_public_article_pdf(deposit.article) as (
        stream, filename
    ):
        size, checksum = _pdf_fingerprint(stream)

        _transition(
            deposit,
            ZenodoDeposit.Status.DRAFT,
            status=ZenodoDeposit.Status.UPLOADING,
            upload_filename=filename,
            upload_size=size,
            upload_checksum=checksum,
        )

        try:
            remote = client.get_deposition(
                deposit.deposition_id
            )

            draft = validate_production_draft(
                deposit, remote
            )

            if remote.get("files") != []:
                raise ProductionWorkflowError(
                    "Remote file inventory is not empty"
                )

            client.upload_pdf(draft, stream, filename)

            verified = client.get_deposition(
                deposit.deposition_id
            )

            validate_production_draft(
                deposit, verified
            )

            if not _remote_file_matches(
                verified, filename, size, checksum
            ):
                raise ProductionWorkflowError(
                    "PDF fingerprint mismatch"
                )

        except Exception:
            _transition(
                deposit,
                ZenodoDeposit.Status.UPLOADING,
                status=ZenodoDeposit.Status.UNKNOWN,
                last_error="PDF upload requires reconciliation",
            )

            raise ProductionWorkflowError(
                "Upload is unverified; do not retry"
            ) from None

        _transition(
            deposit,
            ZenodoDeposit.Status.UPLOADING,
            status=ZenodoDeposit.Status.UPLOADED,
            last_error="",
        )

    return deposit


def reconcile_production_pdf(
    deposit_id, client, *, confirmed=False
):
    deposit = ZenodoDeposit.objects.get(pk=deposit_id)

    _guard(deposit, client, confirmed)

    if deposit.last_error == (
        "Publication requested; verification required"
    ):
        raise ProductionWorkflowError(
            "Publication reconciliation is required"
        )

    if deposit.status != ZenodoDeposit.Status.UNKNOWN:
        raise ProductionWorkflowError(
            "Deposit is not in an uncertain state"
        )

    if (
        not deposit.deposition_id
        or not deposit.upload_filename
        or not deposit.upload_size
        or not deposit.upload_checksum
    ):
        raise ProductionWorkflowError(
            "Upload fingerprint is unavailable"
        )

    snapshot = {
        "pk": deposit.pk,
        "is_sandbox": False,
        "status": ZenodoDeposit.Status.UNKNOWN,
        "deposition_id": deposit.deposition_id,
        "reserved_doi": deposit.reserved_doi,
        "record_url": deposit.record_url,
        "upload_filename": deposit.upload_filename,
        "upload_size": deposit.upload_size,
        "upload_checksum": deposit.upload_checksum,
    }

    remote = client.get_deposition(
        deposit.deposition_id
    )

    validate_production_draft(deposit, remote)

    if not _remote_file_matches(
        remote,
        deposit.upload_filename,
        deposit.upload_size,
        deposit.upload_checksum,
    ):
        raise ProductionWorkflowError(
            "Remote PDF could not be verified"
        )

    changed = ZenodoDeposit.objects.filter(
        **snapshot
    ).update(
        status=ZenodoDeposit.Status.UPLOADED,
        last_error="",
    )

    if changed != 1:
        raise ProductionWorkflowError(
            "Local deposit changed during verification"
        )

    deposit.refresh_from_db()
    return deposit
