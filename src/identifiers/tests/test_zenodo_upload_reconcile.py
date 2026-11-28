from unittest.mock import Mock

from django.test import TestCase

from identifiers.zenodo_models import ZenodoDeposit
from identifiers.zenodo_sandbox import ZenodoError
from identifiers.zenodo_upload_reconcile import (
    ZenodoUploadReconcileError,
    reconcile_sandbox_pdf_upload,
)
from submission.models import Article


class ZenodoUploadReconcileTests(TestCase):

    def setUp(self):
        self.article = Article.objects.create(
            title="Zenodo reconciliation test",
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
            last_error="PDF upload outcome requires reconciliation",
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
                "html": "https://sandbox.zenodo.org/deposit/124",
            },
            "files": [{
                "filename": self.filename,
                "filesize": 1024,
                "checksum": "md5:" + self.checksum,
            }],
        }

        self.client = Mock()
        self.client.get_deposition.return_value = self.remote

    def tearDown(self):
        self.client.upload_pdf.assert_not_called()
        self.client.publish.assert_not_called()
        self.client.create_draft.assert_not_called()

    def reconcile(self, confirmed=False):
        return reconcile_sandbox_pdf_upload(
            self.deposit.pk,
            self.client,
            confirmed=confirmed,
        )

    def assert_status(self, expected):
        self.deposit.refresh_from_db()
        self.assertEqual(self.deposit.status, expected)

    def test_dry_run_does_not_update(self):
        result = self.reconcile()

        self.assertFalse(result["changed"])
        self.assertEqual(result["outcome"], "verified")
        self.assertEqual(
            result["reason"], "confirmation_required"
        )
        self.assert_status(ZenodoDeposit.Status.UNKNOWN)

    def test_confirmed_reconciliation_succeeds(self):
        result = self.reconcile(confirmed=True)

        self.assertTrue(result["changed"])
        self.assertEqual(result["outcome"], "verified")
        self.assertEqual(result["reason"], "reconciled")

        self.assert_status(ZenodoDeposit.Status.UPLOADED)
        self.assertEqual(self.deposit.last_error, "")

    def test_checksum_mismatch_never_updates(self):
        self.remote["files"][0]["checksum"] = "md5:" + "b" * 32

        result = self.reconcile(confirmed=True)

        self.assertFalse(result["changed"])
        self.assertEqual(result["outcome"], "mismatch")
        self.assert_status(ZenodoDeposit.Status.UNKNOWN)

    def test_missing_remote_file_never_updates(self):
        self.remote["files"] = []

        result = self.reconcile(confirmed=True)

        self.assertFalse(result["changed"])
        self.assertEqual(result["outcome"], "unresolved")
        self.assert_status(ZenodoDeposit.Status.UNKNOWN)

    def test_remote_failure_never_updates(self):
        self.client.get_deposition.side_effect = ZenodoError(
            "Sandbox unavailable"
        )

        result = self.reconcile(confirmed=True)

        self.assertFalse(result["changed"])
        self.assertEqual(result["outcome"], "unresolved")
        self.assert_status(ZenodoDeposit.Status.UNKNOWN)

    def test_uploading_state_is_rejected(self):
        self.deposit.status = ZenodoDeposit.Status.UPLOADING
        self.deposit.save(update_fields=["status"])

        with self.assertRaises(ZenodoUploadReconcileError):
            self.reconcile(confirmed=True)

        self.client.get_deposition.assert_not_called()
        self.assert_status(ZenodoDeposit.Status.UPLOADING)

    def test_production_deposit_is_rejected(self):
        self.deposit.is_sandbox = False
        self.deposit.save(update_fields=["is_sandbox"])

        with self.assertRaises(ZenodoUploadReconcileError):
            self.reconcile(confirmed=True)

        self.client.get_deposition.assert_not_called()

    def test_invalid_deposit_id_is_rejected(self):
        for value in (None, 0, -1, True, "1"):
            with self.subTest(value=value):
                with self.assertRaises(ZenodoUploadReconcileError):
                    reconcile_sandbox_pdf_upload(
                        value, self.client, confirmed=True
                    )

        self.client.get_deposition.assert_not_called()

    def test_non_boolean_confirmation_is_rejected(self):
        for value in (None, 1, "yes"):
            with self.subTest(value=value):
                with self.assertRaises(ZenodoUploadReconcileError):
                    reconcile_sandbox_pdf_upload(
                        self.deposit.pk,
                        self.client,
                        confirmed=value,
                    )

        self.client.get_deposition.assert_not_called()

    def test_concurrent_local_change_blocks_update(self):
        def mutate_during_get(remote_id):
            self.assertEqual(remote_id, 124)

            ZenodoDeposit.objects.filter(
                pk=self.deposit.pk
            ).update(upload_checksum="b" * 32)

            return self.remote

        self.client.get_deposition.side_effect = mutate_during_get

        with self.assertRaisesRegex(
            ZenodoUploadReconcileError,
            "Local deposit changed",
        ):
            self.reconcile(confirmed=True)

        self.assert_status(ZenodoDeposit.Status.UNKNOWN)
        self.assertEqual(self.deposit.upload_checksum, "b" * 32)

    def test_repeated_reconciliation_is_rejected(self):
        first = self.reconcile(confirmed=True)
        self.assertTrue(first["changed"])

        with self.assertRaises(ZenodoUploadReconcileError):
            self.reconcile(confirmed=True)

        self.client.get_deposition.assert_called_once_with(124)
        self.assert_status(ZenodoDeposit.Status.UPLOADED)

    def test_published_remote_never_updates(self):
        self.remote["submitted"] = True

        result = self.reconcile(confirmed=True)

        self.assertFalse(result["changed"])
        self.assertEqual(result["outcome"], "unresolved")
        self.assert_status(ZenodoDeposit.Status.UNKNOWN)
