from unittest.mock import patch

from django.db import IntegrityError
from django.test import TestCase

from identifiers.zenodo_models import ZenodoDeposit
from identifiers.zenodo_workflow import (
    ZenodoWorkflowError,
    begin_sandbox_deposit,
)
from submission.models import Article


class ZenodoWorkflowDatabaseTests(TestCase):

    def setUp(self):
        # Journal is intentionally omitted.
        # Preflight is mocked in this test module.
        self.article = Article.objects.create(
            title="Zenodo workflow test article",
        )

        self.metadata = {
            "title": "Zenodo workflow test article",
            "upload_type": "publication",
            "publication_type": "article",
            "prereserve_doi": True,
        }

        preflight_patcher = patch(
            "identifiers.zenodo_workflow."
            "check_zenodo_eligibility"
        )
        metadata_patcher = patch(
            "identifiers.zenodo_workflow."
            "build_zenodo_metadata"
        )

        self.preflight = preflight_patcher.start()
        self.metadata_builder = metadata_patcher.start()

        self.addCleanup(preflight_patcher.stop)
        self.addCleanup(metadata_patcher.stop)

        self.preflight.return_value.eligible = True
        self.preflight.return_value.reason = "OK"

        self.metadata_builder.return_value = self.metadata

    def test_creates_one_local_deposit(self):
        deposit = begin_sandbox_deposit(
            self.article.pk
        )

        self.assertEqual(
            deposit.article_id,
            self.article.pk,
        )
        self.assertTrue(deposit.is_sandbox)

        self.assertEqual(
            deposit.status,
            ZenodoDeposit.Status.UNKNOWN,
        )

        self.assertIsNone(
            deposit.deposition_id
        )

        self.assertEqual(
            deposit.metadata_snapshot,
            self.metadata,
        )

        self.assertEqual(
            ZenodoDeposit.objects.count(),
            1,
        )

    def test_duplicate_local_deposit_is_blocked(self):
        begin_sandbox_deposit(self.article.pk)

        # Real database constraint prevents a second
        # (article, sandbox) record.
        with self.assertRaises(IntegrityError):
            begin_sandbox_deposit(self.article.pk)

        self.assertEqual(
            ZenodoDeposit.objects.count(),
            1,
        )

    def test_ineligible_article_creates_no_record(self):
        self.preflight.return_value.eligible = False
        self.preflight.return_value.reason = (
            "Article already has a DOI"
        )

        with self.assertRaises(ZenodoWorkflowError):
            begin_sandbox_deposit(self.article.pk)

        self.assertFalse(
            ZenodoDeposit.objects.exists()
        )

        self.metadata_builder.assert_not_called()

    def test_metadata_failure_rolls_back(self):
        self.metadata_builder.side_effect = ValueError(
            "Invalid metadata"
        )

        with self.assertRaises(ValueError):
            begin_sandbox_deposit(self.article.pk)

        self.assertFalse(
            ZenodoDeposit.objects.exists()
        )
