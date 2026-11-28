from copy import deepcopy
from unittest.mock import Mock

from django.test import TestCase

from identifiers.zenodo_models import ZenodoDeposit
from identifiers.zenodo_sandbox import ZenodoError
from identifiers.zenodo_upload_recovery import (
    ZenodoUploadRecoveryError,
    inspect_sandbox_pdf_upload,
)
from submission.models import Article


class ZenodoUploadRecoveryTests(TestCase):

    def setUp(self):
        self.article = Article.objects.create(
            title="Zenodo recovery verification test"
        )

        self.filename = f"article-{self.article.pk}.pdf"
        self.checksum = "a" * 32

        self.deposit = ZenodoDeposit.objects.create(
            article=self.article,
            is_sandbox=True,
            status=ZenodoDeposit.Status.UNKNOWN,
            deposition_id=124,
            reserved_doi="10.5072/zenodo.124",
            record_url="https://sandbox.zenodo.org/deposit/124",
            upload_filename=self.filename,
            upload_size=1024,
            upload_checksum=self.checksum,
        )

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
                "html": (
                    "https://sandbox.zenodo.org/deposit/124"
                ),
            },
            "files": [{
                "filename": self.filename,
                "filesize": 1024,
                "checksum": "md5:" + self.checksum,
            }],
        }

        self.client = Mock()
        self.client.get_deposition.return_value = self.remote

    def inspect(self):
        return inspect_sandbox_pdf_upload(
            self.deposit.pk, self.client
        )

    def assert_outcome(self, outcome, reason):
        result = self.inspect()

        self.assertEqual(result["outcome"], outcome)
        self.assertEqual(result["reason"], reason)

        self.deposit.refresh_from_db()

        self.assertEqual(
            self.deposit.status,
            ZenodoDeposit.Status.UNKNOWN,
        )

        self.client.upload_pdf.assert_not_called()
        self.client.publish.assert_not_called()
        self.client.create_draft.assert_not_called()

    def test_matching_fingerprint_is_verified(self):
        self.assert_outcome(
            "verified", "fingerprint_matched"
        )

    def test_wrong_checksum_is_mismatch(self):
        self.remote["files"][0]["checksum"] = "md5:" + "b" * 32

        self.assert_outcome(
            "mismatch", "fingerprint_mismatch"
        )

    def test_wrong_size_is_mismatch(self):
        self.remote["files"][0]["filesize"] = 999

        self.assert_outcome(
            "mismatch", "fingerprint_mismatch"
        )

    def test_missing_file_is_unresolved(self):
        self.remote["files"] = []

        self.assert_outcome(
            "unresolved", "expected_file_not_found"
        )

    def test_missing_inventory_is_unresolved(self):
        del self.remote["files"]

        self.assert_outcome(
            "unresolved", "file_inventory_unavailable"
        )

    def test_duplicate_names_are_unresolved(self):
        self.remote["files"].append(
            deepcopy(self.remote["files"][0])
        )

        self.assert_outcome(
            "unresolved", "ambiguous_remote_files"
        )

    def test_incomplete_fingerprint_is_unresolved(self):
        del self.remote["files"][0]["checksum"]

        self.assert_outcome(
            "unresolved", "remote_fingerprint_incomplete"
        )

    def test_published_remote_is_unresolved(self):
        self.remote["submitted"] = True

        self.assert_outcome(
            "unresolved", "remote_validation_failed"
        )

    def test_remote_error_is_unresolved(self):
        self.client.get_deposition.side_effect = ZenodoError(
            "Sandbox request failed"
        )

        self.assert_outcome(
            "unresolved", "remote_validation_failed"
        )

    def test_invalid_local_fingerprint_is_blocked(self):
        self.deposit.upload_checksum = ""
        self.deposit.save(update_fields=["upload_checksum"])

        with self.assertRaises(ZenodoUploadRecoveryError):
            self.inspect()

        self.client.get_deposition.assert_not_called()

    def test_production_deposit_is_blocked(self):
        self.deposit.is_sandbox = False
        self.deposit.save(update_fields=["is_sandbox"])

        with self.assertRaises(ZenodoUploadRecoveryError):
            self.inspect()

        self.client.get_deposition.assert_not_called()
        self.client.upload_pdf.assert_not_called()
        self.client.publish.assert_not_called()
