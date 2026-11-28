"""
Controlled publication and DOI synchronization.

No automatic publication retries.
"""

from django.conf import settings
from django.db import transaction

from identifiers.models import Identifier
from identifiers.zenodo_models import ZenodoDeposit

from identifiers.zenodo_production_metadata import (
    build_production_metadata,
)

from identifiers.zenodo_production_workflow import (
    ProductionWorkflowError,
    _guard,
    _transition,
    validate_production_draft,
)

from identifiers.zenodo_upload_workflow import (
    _remote_file_matches,
)

from identifiers.zenodo_pdf import open_public_article_pdf
from identifiers.zenodo_upload_workflow import _pdf_fingerprint
from identifiers.zenodo_doi_verification import verify_crossref_doi
from submission.models import Article


PUBLISH_PENDING = "Publication requested; verification required"


def _verify_pdf(deposit, remote):
    if not _remote_file_matches(
        remote,
        deposit.upload_filename,
        deposit.upload_size,
        deposit.upload_checksum,
    ):
        raise ProductionWorkflowError(
            "Remote PDF verification failed"
        )


def _verify_metadata(deposit, remote):
    metadata = remote.get("metadata") or {}

    for key in (
        "title",
        "creators",
        "publication_date",
        "upload_type",
        "publication_type",
        "access_right",
    ):
        if metadata.get(key) != deposit.metadata_snapshot.get(key):
            raise ProductionWorkflowError(
                "Remote metadata mismatch: " + key
            )

    license_value = metadata.get("license")

    if isinstance(license_value, dict):
        license_value = license_value.get("id")

    if license_value != deposit.metadata_snapshot.get("license"):
        raise ProductionWorkflowError("Remote license mismatch")

    if metadata.get("description") != deposit.metadata_snapshot.get(
        "description"
    ):
        raise ProductionWorkflowError("Remote description mismatch")


@transaction.atomic
def _finalize(deposit_id, remote):
    deposit = ZenodoDeposit.objects.select_for_update().get(
        pk=deposit_id,
        is_sandbox=False,
    )

    if (
        deposit.status != ZenodoDeposit.Status.UNKNOWN
        or deposit.last_error != PUBLISH_PENDING
    ):
        raise ProductionWorkflowError(
            "Invalid publication recovery state"
        )

    if (
        remote.get("id") != deposit.deposition_id
        or remote.get("submitted") is not True
        or remote.get("state") != "done"
    ):
        raise ProductionWorkflowError(
            "Remote publication is not confirmed"
        )

    doi = remote.get("doi")

    if not doi or doi != deposit.reserved_doi:
        raise ProductionWorkflowError(
            "Published DOI does not match expected DOI"
        )

    _verify_pdf(deposit, remote)
    _verify_metadata(deposit, remote)

    article = Article.objects.select_for_update().get(
        pk=deposit.article_id
    )

    existing_doi = deposit.metadata_snapshot.get("doi")

    identifiers = list(
        Identifier.objects.select_for_update().filter(
            article=article,
            id_type="doi",
        )
    )

    if existing_doi:
        if (
            len(identifiers) != 1
            or identifiers[0].identifier != doi
            or not identifiers[0].enabled
            or identifiers[0].doi_provider == "zenodo"
        ):
            raise ProductionWorkflowError(
                "Existing DOI conflict"
            )

        # Preserve the existing Crossref identifier.

    else:
        if identifiers:
            raise ProductionWorkflowError(
                "Article acquired another DOI"
            )

        if Identifier.objects.filter(
            id_type="doi",
            identifier__iexact=doi,
        ).exists():
            raise ProductionWorkflowError(
                "DOI is already assigned"
            )

        Identifier.objects.create(
            article=article,
            id_type="doi",
            identifier=doi,
            enabled=True,
            doi_provider=Identifier.DOIProvider.ZENODO,
        )

    deposit.status = ZenodoDeposit.Status.PUBLISHED
    deposit.published_doi = doi
    deposit.record_url = (
        "https://zenodo.org/records/"
        + str(deposit.deposition_id)
    )
    deposit.last_error = ""

    deposit.save(
        update_fields=[
            "status",
            "published_doi",
            "record_url",
            "last_error",
            "updated_at",
        ]
    )

    return deposit


def publish_production_deposit(
    deposit_id, client, *, confirmed=False
):
    deposit = ZenodoDeposit.objects.select_related(
        "article"
    ).get(pk=deposit_id)

    _guard(deposit, client, confirmed)

    if not getattr(
        settings,
        "ZENODO_PRODUCTION_PUBLISH_ENABLED",
        False,
    ):
        raise ProductionWorkflowError(
            "Publication is disabled"
        )

    if deposit.status != ZenodoDeposit.Status.UPLOADED:
        raise ProductionWorkflowError(
            "Verified PDF upload is required"
        )

    metadata = build_production_metadata(
        deposit.article,
        check_existing=False,
    )

    if metadata != deposit.metadata_snapshot:
        raise ProductionWorkflowError(
            "Article metadata changed"
        )

    mode_flag = (
        "ZENODO_PRODUCTION_EXISTING_DOI_ENABLED"
        if metadata.get("doi")
        else "ZENODO_PRODUCTION_NEW_DOI_ENABLED"
    )

    if not getattr(settings, mode_flag, False):
        raise ProductionWorkflowError(
            "DOI mode is disabled"
        )

    if metadata.get("doi"):
        verification = verify_crossref_doi(
            metadata["doi"],
            metadata["title"],
        )

        if verification.get("verified") is not True:
            raise ProductionWorkflowError(
                "Crossref DOI verification failed"
            )

    with open_public_article_pdf(deposit.article) as (
        stream, filename
    ):
        size, checksum = _pdf_fingerprint(stream)

        if (
            filename != deposit.upload_filename
            or size != deposit.upload_size
            or checksum != deposit.upload_checksum
        ):
            raise ProductionWorkflowError(
                "Local PDF changed after upload"
            )

    remote = client.get_deposition(deposit.deposition_id)

    draft = validate_production_draft(deposit, remote)

    _verify_pdf(deposit, remote)
    _verify_metadata(deposit, remote)

    _transition(
        deposit,
        ZenodoDeposit.Status.UPLOADED,
        status=ZenodoDeposit.Status.UNKNOWN,
        last_error=PUBLISH_PENDING,
    )

    try:
        client.publish(draft, confirmed=True)

        remote = client.get_deposition(
            deposit.deposition_id
        )

        return _finalize(deposit.pk, remote)

    except Exception:
        raise ProductionWorkflowError(
            "Publication requires verification. "
            "Do not submit another Publish request."
        ) from None


def reconcile_production_publication(
    deposit_id, client, *, confirmed=False
):
    deposit = ZenodoDeposit.objects.get(pk=deposit_id)

    _guard(deposit, client, confirmed)

    if (
        deposit.status != ZenodoDeposit.Status.UNKNOWN
        or deposit.last_error != PUBLISH_PENDING
    ):
        raise ProductionWorkflowError(
            "No pending publication to reconcile"
        )

    remote = client.get_deposition(
        deposit.deposition_id
    )

    return _finalize(deposit.pk, remote)
