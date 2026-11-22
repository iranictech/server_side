from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from identifiers.zenodo_metadata import (
    ZenodoMetadataError,
    build_zenodo_metadata,
    is_valid_orcid,
    map_author,
    normalize_text,
    resolve_zenodo_license,
)


class ZenodoMetadataTests(SimpleTestCase):

    def setUp(self):
        self.author = SimpleNamespace(
            is_corporate=False,
            dc_name_string="Doe, Jane",
            corporate_name="",
            institution="Example University",
            orcid_uri="https://orcid.org/0000-0002-1825-0097",
        )

        self.article = SimpleNamespace(
            title="<b>Test Article</b>",
            abstract="<p>Research abstract.</p>",
            date_published=datetime(
                2026, 11, 22, tzinfo=timezone.utc
            ),
            license=SimpleNamespace(
                url="https://creativecommons.org/licenses/by/4.0/"
            ),
            frozenauthor_set=MagicMock(),
        )

        self.article.frozenauthor_set.all.return_value = [
            self.author
        ]

        self.preflight = patch(
            "identifiers.zenodo_metadata."
            "check_zenodo_eligibility"
        )

        self.mock_preflight = self.preflight.start()
        self.addCleanup(self.preflight.stop)

        self.mock_preflight.return_value = (
            SimpleNamespace(
                eligible=True,
                reason="OK",
            )
        )

    def test_html_is_removed(self):
        result = normalize_text(
            "<p>Test <b>abstract</b></p>"
        )
        self.assertEqual(result, "Test abstract")

    def test_valid_license(self):
        license_obj = SimpleNamespace(
            url="https://creativecommons.org/licenses/by/4.0/"
        )

        self.assertEqual(
            resolve_zenodo_license(license_obj),
            "cc-by-4.0",
        )

    def test_unsupported_license_is_rejected(self):
        license_obj = SimpleNamespace(
            url="https://creativecommons.org/licenses/by-nc/4.0/"
        )

        with self.assertRaises(ZenodoMetadataError):
            resolve_zenodo_license(license_obj)

    def test_valid_orcid_checksum(self):
        self.assertTrue(
            is_valid_orcid("0000-0002-1825-0097")
        )

    def test_invalid_orcid_checksum(self):
        self.assertFalse(
            is_valid_orcid("0000-0002-1825-0098")
        )

        self.author.orcid_uri = (
            "https://orcid.org/0000-0002-1825-0098"
        )

        with self.assertRaises(ZenodoMetadataError):
            map_author(self.author)

    def test_person_author(self):
        creator = map_author(self.author)

        self.assertEqual(
            creator["name"],
            "Doe, Jane",
        )
        self.assertEqual(
            creator["affiliation"],
            "Example University",
        )
        self.assertEqual(
            creator["orcid"],
            "0000-0002-1825-0097",
        )

    def test_corporate_author(self):
        author = SimpleNamespace(
            is_corporate=True,
            corporate_name="Example Research Institute",
        )

        creator = map_author(author)

        self.assertEqual(
            creator,
            {"name": "Example Research Institute"},
        )

    def test_invalid_orcid_is_rejected(self):
        self.author.orcid_uri = (
            "https://orcid.org/invalid"
        )

        with self.assertRaises(ZenodoMetadataError):
            map_author(self.author)

    def test_metadata_payload(self):
        metadata = build_zenodo_metadata(
            self.article
        )

        self.assertEqual(
            metadata["title"],
            "Test Article",
        )
        self.assertEqual(
            metadata["description"],
            "Research abstract.",
        )
        self.assertEqual(
            metadata["license"],
            "cc-by-4.0",
        )
        self.assertEqual(
            metadata["publication_date"],
            "2026-11-22",
        )
        self.assertEqual(
            metadata["publication_type"],
            "article",
        )
        self.assertTrue(
            metadata["prereserve_doi"]
        )

    def test_ineligible_article_is_rejected(self):
        self.mock_preflight.return_value = (
            SimpleNamespace(
                eligible=False,
                reason="Article already has a DOI",
            )
        )

        with self.assertRaises(ZenodoMetadataError):
            build_zenodo_metadata(self.article)

    def test_missing_abstract_is_rejected(self):
        self.article.abstract = ""

        with self.assertRaises(ZenodoMetadataError):
            build_zenodo_metadata(self.article)
