from copy import deepcopy
from types import SimpleNamespace
from unittest import TestCase

from identifiers.zenodo_upload_validation import (
    ZenodoUploadValidationError,
    validate_sandbox_remote_draft,
)


class ZenodoUploadValidationTests(TestCase):

    def setUp(self):
        self.deposit = SimpleNamespace(
            is_sandbox=True,
            deposition_id=124,
            reserved_doi="10.5072/zenodo.124",
            record_url="https://sandbox.zenodo.org/deposit/124",
        )

        self.remote = {
            "id": 124,
            "submitted": False,
            "metadata": {
                "prereserve_doi": {
                    "doi": "10.5072/zenodo.124"
                }
            },
            "links": {
                "bucket": (
                    "https://sandbox.zenodo.org/"
                    "api/files/example"
                ),
                "html": (
                    "https://sandbox.zenodo.org/deposit/124"
                ),
            },
        }

    def validate(self, remote=None):
        return validate_sandbox_remote_draft(
            self.deposit,
            self.remote if remote is None else remote,
        )

    def test_valid_remote_draft(self):
        draft = self.validate()
        self.assertEqual(draft.deposition_id, 124)
        self.assertEqual(
            draft.reserved_doi, self.deposit.reserved_doi
        )

    def test_wrong_remote_id(self):
        remote = deepcopy(self.remote)
        remote["id"] = 999

        with self.assertRaises(ZenodoUploadValidationError):
            self.validate(remote)

    def test_missing_submitted_is_blocked(self):
        remote = deepcopy(self.remote)
        del remote["submitted"]

        with self.assertRaises(ZenodoUploadValidationError):
            self.validate(remote)

    def test_published_remote_is_blocked(self):
        remote = deepcopy(self.remote)
        remote["submitted"] = True

        with self.assertRaises(ZenodoUploadValidationError):
            self.validate(remote)

    def test_doi_mismatch(self):
        remote = deepcopy(self.remote)
        remote["metadata"]["prereserve_doi"]["doi"] = (
            "10.5072/zenodo.999"
        )

        with self.assertRaises(ZenodoUploadValidationError):
            self.validate(remote)

    def test_external_bucket_is_blocked(self):
        remote = deepcopy(self.remote)
        remote["links"]["bucket"] = (
            "https://attacker.example/api/files/test"
        )

        with self.assertRaises(ZenodoUploadValidationError):
            self.validate(remote)

    def test_production_deposit_is_blocked(self):
        self.deposit.is_sandbox = False

        with self.assertRaises(ZenodoUploadValidationError):
            self.validate()

    def test_wrong_local_url_is_blocked(self):
        self.deposit.record_url = (
            "https://sandbox.zenodo.org/deposit/999"
        )

        with self.assertRaises(ZenodoUploadValidationError):
            self.validate()
