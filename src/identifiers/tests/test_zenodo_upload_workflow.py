from contextlib import contextmanager
from io import BytesIO
from unittest.mock import Mock, patch

from django.test import TestCase

from identifiers.zenodo_models import ZenodoDeposit
from identifiers.zenodo_sandbox import ZenodoError
from identifiers.zenodo_upload_workflow import (
    upload_sandbox_article_pdf,
)
from identifiers.zenodo_workflow import ZenodoWorkflowError
from submission.models import Article


PDF_DATA = b"%PDF-1.4\nTest PDF data\n%%EOF"
PDF_NAME = "article-1.pdf"


class ZenodoUploadWorkflowTests(TestCase):

    def setUp(self):
        self.article = Article.objects.create(
            title="Zenodo PDF upload test",
        )

        self.deposit = ZenodoDeposit.objects.create(
            article=self.article,
            is_sandbox=True,
            status=ZenodoDeposit.Status.DRAFT,
            deposition_id=124,
            reserved_doi="10.5072/zenodo.124",
            record_url="https://sandbox.zenodo.org/deposit/124",
        )

        self.filename = f"article-{self.article.pk}.pdf"

        import hashlib
        checksum = hashlib.md5(PDF_DATA).hexdigest()

        self.remote = {
            "id": 124,
            "submitted": False,
            "metadata": {
                "prereserve_doi": {
                    "doi": "10.5072/zenodo.124",
                },
            },
            "links": {
                "bucket": (
                    "https://sandbox.zenodo.org/api/files/example"
                ),
                "html": "https://sandbox.zenodo.org/deposit/124",
            },
            "files": [],
        }

        self.verified = {
            **self.remote,
            "files": [{
                "filename": self.filename,
                "filesize": len(PDF_DATA),
                "checksum": "md5:" + checksum,
            }],
        }

        self.client = Mock()
        self.client.get_deposition.side_effect = [
            self.remote,
            self.verified,
        ]
        self.client.upload_pdf.return_value = {
            "key": self.filename,
        }

        @contextmanager
        def fake_pdf(article):
            self.assertEqual(article.pk, self.article.pk)
            with BytesIO(PDF_DATA) as stream:
                yield stream, self.filename

        patcher = patch(
            "identifiers.zenodo_upload_workflow."
            "open_public_article_pdf",
            side_effect=fake_pdf,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def assert_status(self, status):
        self.deposit.refresh_from_db()
        self.assertEqual(self.deposit.status, status)

    def test_successful_upload(self):
        result = upload_sandbox_article_pdf(
            self.deposit.pk, self.client
        )

        self.assertEqual(
            result.status,
            ZenodoDeposit.Status.UPLOADED,
        )
        self.assert_status(ZenodoDeposit.Status.UPLOADED)

        self.client.upload_pdf.assert_called_once()
        self.assertEqual(
            self.client.get_deposition.call_count, 2
        )
        self.client.publish.assert_not_called()

    def test_duplicate_upload_is_blocked(self):
        upload_sandbox_article_pdf(
            self.deposit.pk, self.client
        )

        with self.assertRaises(ZenodoWorkflowError):
            upload_sandbox_article_pdf(
                self.deposit.pk, self.client
            )

        self.client.upload_pdf.assert_called_once()

    def test_existing_remote_file_is_blocked(self):
        self.remote["files"] = [
            {"filename": self.filename}
        ]

        with self.assertRaises(ZenodoWorkflowError):
            upload_sandbox_article_pdf(
                self.deposit.pk, self.client
            )

        self.client.upload_pdf.assert_not_called()
        self.assert_status(ZenodoDeposit.Status.UNKNOWN)

    def test_network_failure_becomes_unknown(self):
        self.client.get_deposition.side_effect = None
        self.client.get_deposition.return_value = self.remote
        self.client.upload_pdf.side_effect = ZenodoError(
            "Request failed"
        )

        with self.assertRaisesRegex(
            ZenodoWorkflowError, "automatic retry"
        ):
            upload_sandbox_article_pdf(
                self.deposit.pk, self.client
            )

        self.assert_status(ZenodoDeposit.Status.UNKNOWN)
        self.client.upload_pdf.assert_called_once()

    def test_invalid_upload_response(self):
        self.client.upload_pdf.return_value = {}

        with self.assertRaises(ZenodoWorkflowError):
            upload_sandbox_article_pdf(
                self.deposit.pk, self.client
            )

        self.assert_status(ZenodoDeposit.Status.UNKNOWN)

    def test_wrong_checksum_is_blocked(self):
        self.verified["files"][0]["checksum"] = (
            "md5:" + "0" * 32
        )

        with self.assertRaises(ZenodoWorkflowError):
            upload_sandbox_article_pdf(
                self.deposit.pk, self.client
            )

        self.assert_status(ZenodoDeposit.Status.UNKNOWN)

    def test_published_remote_is_blocked(self):
        self.remote["submitted"] = True

        with self.assertRaises(ZenodoWorkflowError):
            upload_sandbox_article_pdf(
                self.deposit.pk, self.client
            )

        self.client.upload_pdf.assert_not_called()
        self.assert_status(ZenodoDeposit.Status.UNKNOWN)

    def test_production_deposit_is_blocked(self):
        self.deposit.is_sandbox = False
        self.deposit.save(update_fields=["is_sandbox"])

        with self.assertRaises(ZenodoWorkflowError):
            upload_sandbox_article_pdf(
                self.deposit.pk, self.client
            )

        self.client.get_deposition.assert_not_called()
        self.client.upload_pdf.assert_not_called()
        self.assert_status(ZenodoDeposit.Status.DRAFT)

    def test_unknown_state_cannot_retry(self):
        self.deposit.status = ZenodoDeposit.Status.UNKNOWN
        self.deposit.save(update_fields=["status"])

        with self.assertRaises(ZenodoWorkflowError):
            upload_sandbox_article_pdf(
                self.deposit.pk, self.client
            )

        self.client.upload_pdf.assert_not_called()

    def test_missing_remote_inventory(self):
        del self.remote["files"]

        with self.assertRaises(ZenodoWorkflowError):
            upload_sandbox_article_pdf(
                self.deposit.pk, self.client
            )

        self.client.upload_pdf.assert_not_called()
        self.assert_status(ZenodoDeposit.Status.UNKNOWN)
