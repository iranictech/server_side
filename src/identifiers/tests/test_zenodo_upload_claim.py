from django.test import TestCase

from identifiers.zenodo_models import ZenodoDeposit
from identifiers.zenodo_workflow import (
    ZenodoWorkflowError,
    claim_sandbox_pdf_upload,
)
from submission.models import Article


def _claim(deposit_id):
    return claim_sandbox_pdf_upload(
        deposit_id,
        filename="article-test.pdf",
        size=100,
        checksum="a" * 32,
    )


class ZenodoUploadClaimTests(TestCase):

    def setUp(self):
        self.article = Article.objects.create(
            title="Zenodo upload claim test"
        )

        self.deposit = ZenodoDeposit.objects.create(
            article=self.article,
            is_sandbox=True,
            status=ZenodoDeposit.Status.DRAFT,
            deposition_id=124,
            reserved_doi="10.5072/zenodo.124",
        )

    def test_valid_claim(self):
        result = _claim(
            self.deposit.pk
        )

        self.assertEqual(
            result.status,
            ZenodoDeposit.Status.UPLOADING,
        )

        self.deposit.refresh_from_db()

        self.assertEqual(
            self.deposit.status,
            ZenodoDeposit.Status.UPLOADING,
        )

    def test_duplicate_claim_is_blocked(self):
        _claim(self.deposit.pk)

        with self.assertRaises(ZenodoWorkflowError):
            _claim(self.deposit.pk)

        self.deposit.refresh_from_db()

        self.assertEqual(
            self.deposit.status,
            ZenodoDeposit.Status.UPLOADING,
        )

    def test_missing_remote_id_is_blocked(self):
        self.deposit.deposition_id = None
        self.deposit.save(update_fields=["deposition_id"])

        with self.assertRaises(ZenodoWorkflowError):
            _claim(self.deposit.pk)

        self.deposit.refresh_from_db()
        self.assertEqual(
            self.deposit.status,
            ZenodoDeposit.Status.DRAFT,
        )

    def test_missing_reserved_doi_is_blocked(self):
        self.deposit.reserved_doi = ""
        self.deposit.save(update_fields=["reserved_doi"])

        with self.assertRaises(ZenodoWorkflowError):
            _claim(self.deposit.pk)

        self.deposit.refresh_from_db()
        self.assertEqual(
            self.deposit.status,
            ZenodoDeposit.Status.DRAFT,
        )

    def test_production_deposit_is_blocked(self):
        self.deposit.is_sandbox = False
        self.deposit.save(update_fields=["is_sandbox"])

        with self.assertRaises(ZenodoWorkflowError):
            _claim(self.deposit.pk)

        self.deposit.refresh_from_db()
        self.assertEqual(
            self.deposit.status,
            ZenodoDeposit.Status.DRAFT,
        )

    def test_invalid_id_is_blocked(self):
        for invalid_id in (None, 0, -1, "124", True):
            with self.subTest(invalid_id=invalid_id):
                with self.assertRaises(ZenodoWorkflowError):
                    _claim(invalid_id)
