from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from identifiers.zenodo_service import (
    check_zenodo_eligibility,
)


class ZenodoPreflightTests(SimpleTestCase):

    def setUp(self):
        self.article = SimpleNamespace(
            pk=40,
            journal_id=1,
            date_published="2026-11-22",
            license_id=1,
            frozenauthor_set=MagicMock(),
            pdfs=MagicMock(),
        )

        self.article.frozenauthor_set.exists.return_value = True
        self.article.pdfs.exists.return_value = True

        self.doi_patcher = patch(
            "identifiers.zenodo_service.Identifier.objects"
        )
        self.deposit_patcher = patch(
            "identifiers.zenodo_service.ZenodoDeposit.objects"
        )

        self.doi_manager = self.doi_patcher.start()
        self.deposit_manager = self.deposit_patcher.start()

        self.addCleanup(self.doi_patcher.stop)
        self.addCleanup(self.deposit_patcher.stop)

        self.doi_manager.filter.return_value \
            .order_by.return_value \
            .values_list.return_value = []

        self.deposit_manager.filter.return_value \
            .first.return_value = None

    def test_article_without_doi_is_eligible(self):
        result = check_zenodo_eligibility(self.article)

        self.assertTrue(result.eligible)
        self.assertEqual(result.existing_dois, ())

    def test_existing_doi_is_blocked(self):
        self.doi_manager.filter.return_value \
            .order_by.return_value \
            .values_list.return_value = [
                "10.1234/existing"
            ]

        result = check_zenodo_eligibility(self.article)

        self.assertFalse(result.eligible)
        self.assertEqual(
            result.reason,
            "Article already has a DOI",
        )

        self.deposit_manager.filter.assert_not_called()

    def test_disabled_doi_is_also_blocked(self):
        self.doi_manager.filter.return_value \
            .order_by.return_value \
            .values_list.return_value = [
                "10.1234/disabled"
            ]

        result = check_zenodo_eligibility(self.article)

        self.assertFalse(result.eligible)

        # DOI query must not filter by enabled=True.
        kwargs = self.doi_manager.filter.call_args.kwargs
        self.assertNotIn("enabled", kwargs)

    def test_existing_deposit_is_blocked(self):
        self.deposit_manager.filter.return_value \
            .first.return_value = SimpleNamespace(
                deposition_id=647342
            )

        result = check_zenodo_eligibility(self.article)

        self.assertFalse(result.eligible)
        self.assertEqual(
            result.existing_deposition_id,
            647342,
        )

    def test_missing_publication_date_is_blocked(self):
        self.article.date_published = None

        result = check_zenodo_eligibility(self.article)

        self.assertFalse(result.eligible)
        self.assertIn("publication date", result.reason)

    def test_missing_license_is_blocked(self):
        self.article.license_id = None

        result = check_zenodo_eligibility(self.article)

        self.assertFalse(result.eligible)
        self.assertIn("license", result.reason)

    def test_missing_authors_is_blocked(self):
        self.article.frozenauthor_set.exists.return_value = False

        result = check_zenodo_eligibility(self.article)

        self.assertFalse(result.eligible)
        self.assertIn("authors", result.reason)

    def test_missing_pdf_is_blocked(self):
        self.article.pdfs.exists.return_value = False

        result = check_zenodo_eligibility(self.article)

        self.assertFalse(result.eligible)
        self.assertIn("PDF", result.reason)

    def test_missing_journal_is_blocked(self):
        self.article.journal_id = None

        result = check_zenodo_eligibility(self.article)

        self.assertFalse(result.eligible)
        self.assertIn("journal", result.reason)

    def test_unsaved_article_is_rejected(self):
        self.article.pk = None

        with self.assertRaises(ValueError):
            check_zenodo_eligibility(self.article)
