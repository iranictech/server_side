"""
Read-only inspection of known Zenodo Sandbox deposits.

Does not create drafts, retry operations, or update the database.
"""

from identifiers.zenodo_models import ZenodoDeposit
from identifiers.zenodo_sandbox import ZenodoError


class ZenodoRecoveryError(RuntimeError):
    pass


def inspect_known_sandbox_deposit(deposit_id, client):
    """
    Read a remote deposit only when its ID is already persisted.

    UNKNOWN records without a deposition_id require manual
    reconciliation and must not be retried automatically.
    """
    deposit = ZenodoDeposit.objects.get(pk=deposit_id)

    if not deposit.is_sandbox:
        raise ZenodoRecoveryError(
            "Production deposits are not supported"
        )

    remote_id = deposit.deposition_id

    if type(remote_id) is not int or remote_id <= 0:
        raise ZenodoRecoveryError(
            "Remote deposition ID is unknown; manual review required"
        )

    try:
        remote = client.get_deposition(remote_id)
    except ZenodoError as exc:
        raise ZenodoRecoveryError(
            "Remote deposit could not be verified"
        ) from exc

    if (
        not isinstance(remote, dict)
        or type(remote.get("id")) is not int
        or remote["id"] != remote_id
    ):
        raise ZenodoRecoveryError(
            "Remote deposition identity mismatch"
        )

    return {
        "local_deposit_id": deposit.pk,
        "remote_deposition_id": remote_id,
        "local_status": deposit.status,
        "remote_submitted": remote.get("submitted"),
        "remote_doi": remote.get("doi"),
    }
