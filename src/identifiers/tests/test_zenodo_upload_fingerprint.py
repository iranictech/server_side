from django.test import TestCase

from identifiers.zenodo_models import ZenodoDeposit
from identifiers.zenodo_workflow import (
    ZenodoWorkflowError,
    claim_sandbox_pdf_upload,
)
from submission.models import Article


class ZenodoUploadFingerprintTests(TestCase):

    def setUp(self):
        self.article = Article.objects.create(
            title="Zenodo fingerprint test"
        )

        self.deposit = ZenodoDeposit.objects.create(
            article=self.article,
            is_sandbox=True,
            status=ZenodoDeposit.Status.DRAFT,
            deposition_id=124,
            reserved_doi="10.5072/zenodo.124",
        )

        self.filename = f"article-{self.article.pk}.pdf"
        self.size = 1024
        self.checksum = "a" * 32

    def claim(self, **overrides):
        values = {
            "filename": self.filename,
            "size": self.size,
            "checksum": self.checksum,
        }
        values.update(overrides)

        return claim_sandbox_pdf_upload(
            self.deposit.pk,
            **values,
        )

    def test_fingerprint_is_persisted(self):
        result = self.claim()

        self.assertEqual(
            result.status,
            ZenodoDeposit.Status.UPLOADING,
        )

        self.deposit.refresh_from_db()

        self.assertEqual(
            self.deposit.upload_filename,
            self.filename,
        )
        self.assertEqual(
            self.deposit.upload_size,
            self.size,
        )
        self.assertEqual(
            self.deposit.upload_checksum,
            self.checksum,
        )

    def test_duplicate_claim_preserves_fingerprint(self):
        self.claim()

        with self.assertRaises(ZenodoWorkflowError):
            self.claim(
                filename="different.pdf",
                checksum="b" * 32,
            )

        self.deposit.refresh_from_db()

        self.assertEqual(
            self.deposit.upload_filename,
            self.filename,
        )
        self.assertEqual(
            self.deposit.upload_checksum,
            self.checksum,
        )

    def test_invalid_filename_is_rejected(self):
        for filename in (
            "",
            "../paper.pdf",
            "/tmp/paper.pdf",
            "paper.txt",
            "folder\\paper.pdf",
        ):
            with self.subTest(filename=filename):
                with self.assertRaises(ZenodoWorkflowError):
                    self.claim(filename=filename)

        self.deposit.refresh_from_db()
        self.assertEqual(
            self.deposit.status,
            ZenodoDeposit.Status.DRAFT,
        )
        self.assertEqual(self.deposit.upload_filename, "")

    def test_invalid_size_is_rejected(self):
        for size in (None, 0, -1, True, "1024"):
            with self.subTest(size=size):
                with self.assertRaises(ZenodoWorkflowError):
                    self.claim(size=size)

        self.deposit.refresh_from_db()
        self.assertEqual(
            self.deposit.status,
            ZenodoDeposit.Status.DRAFT,
        )

    def test_invalid_checksum_is_rejected(self):
        for checksum in (
            "",
            "not-a-checksum",
            "A" * 32,
            "a" * 31,
            "g" * 32,
        ):
            with self.subTest(checksum=checksum):
                with self.assertRaises(ZenodoWorkflowError):
                    self.claim(checksum=checksum)

        self.deposit.refresh_from_db()
        self.assertEqual(
            self.deposit.status,
            ZenodoDeposit.Status.DRAFT,
        )

    def test_existing_fingerprint_blocks_claim(self):
        self.deposit.upload_checksum = "b" * 32
        self.deposit.save(update_fields=["upload_checksum"])

        with self.assertRaises(ZenodoWorkflowError):
            self.claim()

        self.deposit.refresh_from_db()

        self.assertEqual(
            self.deposit.status,
            ZenodoDeposit.Status.DRAFT,
        )
        self.assertEqual(
            self.deposit.upload_checksum,
            "b" * 32,
        )
