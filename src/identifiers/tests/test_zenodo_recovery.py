from unittest.mock import Mock

from django.test import TestCase

from identifiers.zenodo_models import ZenodoDeposit
from identifiers.zenodo_recovery import (
    ZenodoRecoveryError,
    inspect_known_sandbox_deposit,
)
from identifiers.zenodo_sandbox import ZenodoError
from submission.models import Article


class ZenodoRecoveryTests(TestCase):

    def setUp(self):
        self.article = Article.objects.create(
            title="Zenodo recovery test article",
        )

        self.deposit = ZenodoDeposit.objects.create(
            article=self.article,
            is_sandbox=True,
            deposition_id=124,
            reserved_doi="10.5072/zenodo.124",
            status=ZenodoDeposit.Status.UNKNOWN,
        )

        self.client = Mock()
        self.client.get_deposition.return_value = {
            "id": 124,
            "submitted": False,
            "doi": None,
        }

    def test_known_deposit_is_inspected(self):
        result = inspect_known_sandbox_deposit(
            self.deposit.pk,
            self.client,
        )

        self.assertEqual(
            result["remote_deposition_id"], 124
        )
        self.assertFalse(result["remote_submitted"])

        self.client.get_deposition.assert_called_once_with(124)

    def test_unknown_remote_id_is_blocked(self):
        self.deposit.deposition_id = None
        self.deposit.save(update_fields=["deposition_id"])

        with self.assertRaisesRegex(
            ZenodoRecoveryError,
            "manual review required",
        ):
            inspect_known_sandbox_deposit(
                self.deposit.pk,
                self.client,
            )

        self.client.get_deposition.assert_not_called()

    def test_remote_identity_mismatch_is_blocked(self):
        self.client.get_deposition.return_value = {
            "id": 999,
            "submitted": False,
        }

        with self.assertRaisesRegex(
            ZenodoRecoveryError,
            "identity mismatch",
        ):
            inspect_known_sandbox_deposit(
                self.deposit.pk,
                self.client,
            )

    def test_remote_error_is_handled(self):
        self.client.get_deposition.side_effect = ZenodoError(
            "Sandbox request failed"
        )

        with self.assertRaisesRegex(
            ZenodoRecoveryError,
            "could not be verified",
        ):
            inspect_known_sandbox_deposit(
                self.deposit.pk,
                self.client,
            )

    def test_production_deposit_is_blocked(self):
        self.deposit.is_sandbox = False
        self.deposit.save(update_fields=["is_sandbox"])

        with self.assertRaisesRegex(
            ZenodoRecoveryError,
            "Production deposits",
        ):
            inspect_known_sandbox_deposit(
                self.deposit.pk,
                self.client,
            )

        self.client.get_deposition.assert_not_called()

    def test_inspection_does_not_modify_local_record(self):
        before = ZenodoDeposit.objects.get(pk=self.deposit.pk)

        inspect_known_sandbox_deposit(
            self.deposit.pk,
            self.client,
        )

        after = ZenodoDeposit.objects.get(pk=self.deposit.pk)

        self.assertEqual(before.status, after.status)
        self.assertEqual(
            before.deposition_id,
            after.deposition_id,
        )
        self.assertEqual(
            before.reserved_doi,
            after.reserved_doi,
        )
        self.assertEqual(
            ZenodoDeposit.objects.count(),
            1,
        )
