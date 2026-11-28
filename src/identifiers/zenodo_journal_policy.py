"""Journal-level DOI provider settings."""

from django.core.exceptions import ObjectDoesNotExist
from utils import setting_handler


def get_doi_setting(journal, name, default=None):
    try:
        setting = setting_handler.get_setting(
            "Identifiers", name, journal
        )
        return setting.processed_value
    except ObjectDoesNotExist:
        return default


def zenodo_enabled(journal):
    return get_doi_setting(
        journal, "use_zenodo", False
    ) is True


def default_doi_provider(journal):
    value = get_doi_setting(
        journal, "doi_provider", "crossref"
    )

    value = str(value).strip().lower()

    if value in ("crossref", "zenodo", "manual"):
        return value

    return "invalid"


def zenodo_archive_enabled(journal):
    return get_doi_setting(
        journal, "zenodo_archive_existing_doi", False
    ) is True


def automatic_crossref_enabled(journal):
    return default_doi_provider(journal) == "crossref"


def zenodo_new_doi_enabled(journal):
    return (
        zenodo_enabled(journal)
        and get_doi_setting(
            journal, "zenodo_allow_new_doi", False
        ) is True
        and default_doi_provider(journal) in ("zenodo", "manual")
    )


def zenodo_publication_enabled(journal):
    return (
        zenodo_enabled(journal)
        and get_doi_setting(
            journal, "zenodo_allow_publication", False
        ) is True
    )
