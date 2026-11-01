"""Read-only reviewer recommendations from internal and external sources."""

from .services import get_internal_matches
from .identity import normalize_orcid, resolve_janeway_orcid
from .orcid_client import fetch_public_email
from .openalex import (
    discover_external_researchers,
    OpenAlexDiscoveryError,
)


def build_combined_matches(
    article,
    editor,
    *,
    public_topics,
    internal_limit=20,
    external_limit=15,
    allow_external=False,
    allow_orcid_email=False,
):
    internal = get_internal_matches(
        article,
        editor,
        limit=internal_limit,
    )

    external = []
    excluded_article_authors = 0
    orcid_lookups = 0

    if not public_topics:
        external_status = "not_requested"
    elif not allow_external:
        external_status = "disabled"
    else:
        try:
            external = discover_external_researchers(
                public_topics,
                limit=external_limit,
            )
            enriched = []

            for candidate in external:
                item = dict(candidate)

                orcid = normalize_orcid(
                    item.get("orcid")
                )

                if item.get("orcid_status") == "ambiguous":
                    identity_status = "ambiguous_orcid"
                else:
                    identity_status = resolve_janeway_orcid(
                        article,
                        orcid,
                    )

                if identity_status == "article_author":
                    excluded_article_authors += 1
                    continue

                item["orcid"] = orcid or None
                item["identity_status"] = identity_status
                item["identity_verified"] = False
                item["email"] = None
                item["email_source"] = None
                item["invitation_ready"] = False

                if identity_status == "existing_janeway_account":
                    item["email_status"] = "use_janeway_account"

                elif identity_status == "new_external":
                    item["email_status"] = "disabled"

                    if allow_orcid_email:
                        # Bound synchronous network calls.
                        # A queued lookup service can replace this later.
                        if orcid_lookups < 3:
                            orcid_lookups += 1

                            email_data = fetch_public_email(
                                orcid,
                                enabled=True,
                            )

                            item["email"] = email_data["email"]
                            item["email_status"] = email_data["status"]
                            item["email_source"] = email_data["source"]
                        else:
                            item["email_status"] = "not_checked_limit"

                else:
                    item["email_status"] = "not_checked"

                enriched.append(item)

            external = enriched
            external_status = "completed"
        except OpenAlexDiscoveryError:
            external_status = "unavailable"

    return {
        "article_id": article.pk,
        "internal_priority": True,
        "matching_method": "initial_keyword_and_public_work_discovery",
        "semantic_matching_enabled": False,
        "automatic_invitation": False,
        "coi_screening_complete": False,
        "cross_source_identity_resolution_complete": False,
        "external_status": external_status,
        "excluded_article_authors": excluded_article_authors,
        "orcid_email_lookup_enabled": bool(
            allow_external and allow_orcid_email
        ),
        "counts": {
            "internal": len(internal),
            "external": len(external),
        },
        "results": {
            "internal": internal,
            "external": external,
        },
    }
