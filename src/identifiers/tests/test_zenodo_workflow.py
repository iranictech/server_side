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
            ZenodoDeposit.Status.READY,
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

    def test_claim_ready_deposit(self):
        deposit = begin_sandbox_deposit(self.article.pk)

        from identifiers.zenodo_workflow import (
            claim_sandbox_draft_creation,
        )

        claimed = claim_sandbox_draft_creation(deposit.pk)

        self.assertEqual(
            claimed.status,
            ZenodoDeposit.Status.CREATING,
        )

        deposit.refresh_from_db()
        self.assertEqual(
            deposit.status,
            ZenodoDeposit.Status.CREATING,
        )

    def test_duplicate_claim_is_blocked(self):
        from identifiers.zenodo_workflow import (
            claim_sandbox_draft_creation,
        )

        deposit = begin_sandbox_deposit(self.article.pk)
        claim_sandbox_draft_creation(deposit.pk)

        with self.assertRaises(ZenodoWorkflowError):
            claim_sandbox_draft_creation(deposit.pk)

    def test_unknown_deposit_cannot_be_claimed(self):
        from identifiers.zenodo_workflow import (
            claim_sandbox_draft_creation,
        )

        deposit = begin_sandbox_deposit(self.article.pk)
        deposit.status = ZenodoDeposit.Status.UNKNOWN
        deposit.save(update_fields=["status"])

        with self.assertRaises(ZenodoWorkflowError):
            claim_sandbox_draft_creation(deposit.pk)

        deposit.refresh_from_db()
        self.assertEqual(
            deposit.status,
            ZenodoDeposit.Status.UNKNOWN,
        )

    def test_production_deposit_cannot_be_claimed(self):
        from identifiers.zenodo_workflow import (
            claim_sandbox_draft_creation,
        )

        deposit = begin_sandbox_deposit(self.article.pk)
        deposit.is_sandbox = False
        deposit.save(update_fields=["is_sandbox"])

        with self.assertRaises(ZenodoWorkflowError):
            claim_sandbox_draft_creation(deposit.pk)

        deposit.refresh_from_db()
        self.assertEqual(
            deposit.status,
            ZenodoDeposit.Status.READY,
        )

    def test_remote_draft_success(self):
        from unittest.mock import Mock
        from identifiers.zenodo_sandbox import Draft
        from identifiers.zenodo_workflow import (
            create_sandbox_remote_draft,
        )

        deposit = begin_sandbox_deposit(self.article.pk)
        client = Mock()

        client.create_draft.return_value = Draft(
            124,
            "10.5072/zenodo.124",
            "https://sandbox.zenodo.org/api/files/test",
            "https://sandbox.zenodo.org/deposit/124",
        )

        result = create_sandbox_remote_draft(
            deposit.pk, client
        )

        self.assertEqual(
            result.status, ZenodoDeposit.Status.DRAFT
        )
        self.assertEqual(result.deposition_id, 124)
        self.assertEqual(
            result.reserved_doi, "10.5072/zenodo.124"
        )

        client.create_draft.assert_called_once_with(
            self.metadata
        )

    def test_remote_failure_becomes_unknown(self):
        from unittest.mock import Mock
        from identifiers.zenodo_sandbox import ZenodoError
        from identifiers.zenodo_workflow import (
            create_sandbox_remote_draft,
        )

        deposit = begin_sandbox_deposit(self.article.pk)
        client = Mock()

        client.create_draft.side_effect = ZenodoError(
            "Network request failed"
        )

        with self.assertRaisesRegex(
            ZenodoWorkflowError, "automatic retry"
        ):
            create_sandbox_remote_draft(
                deposit.pk, client
            )

        deposit.refresh_from_db()

        self.assertEqual(
            deposit.status, ZenodoDeposit.Status.UNKNOWN
        )
        self.assertIsNone(deposit.deposition_id)
        self.assertEqual(client.create_draft.call_count, 1)

    def test_invalid_remote_result_becomes_unknown(self):
        from unittest.mock import Mock
        from identifiers.zenodo_workflow import (
            create_sandbox_remote_draft,
        )

        deposit = begin_sandbox_deposit(self.article.pk)
        client = Mock()
        client.create_draft.return_value = {"id": 124}

        with self.assertRaises(ZenodoWorkflowError):
            create_sandbox_remote_draft(
                deposit.pk, client
            )

        deposit.refresh_from_db()

        self.assertEqual(
            deposit.status, ZenodoDeposit.Status.UNKNOWN
        )
        self.assertIsNone(deposit.deposition_id)

    def test_remote_creation_cannot_be_repeated(self):
        from unittest.mock import Mock
        from identifiers.zenodo_sandbox import Draft
        from identifiers.zenodo_workflow import (
            create_sandbox_remote_draft,
        )

        deposit = begin_sandbox_deposit(self.article.pk)
        client = Mock()

        client.create_draft.return_value = Draft(
            124,
            "10.5072/zenodo.124",
            "https://sandbox.zenodo.org/api/files/test",
            "https://sandbox.zenodo.org/deposit/124",
        )

        create_sandbox_remote_draft(
            deposit.pk, client
        )

        with self.assertRaises(ZenodoWorkflowError):
            create_sandbox_remote_draft(
                deposit.pk, client
            )

        self.assertEqual(client.create_draft.call_count, 1)

    def test_changed_state_blocks_remote_persistence(self):
        from unittest.mock import Mock
        from identifiers.zenodo_sandbox import Draft
        from identifiers.zenodo_workflow import (
            create_sandbox_remote_draft,
        )

        deposit = begin_sandbox_deposit(self.article.pk)
        client = Mock()

        def remote_operation(metadata):
            # Simulate another operation changing local state
            # before the remote response is persisted.
            ZenodoDeposit.objects.filter(
                pk=deposit.pk,
            ).update(
                status=ZenodoDeposit.Status.UNKNOWN
            )

            return Draft(
                124,
                "10.5072/zenodo.124",
                "https://sandbox.zenodo.org/api/files/test",
                "https://sandbox.zenodo.org/deposit/124",
            )

        client.create_draft.side_effect = remote_operation

        with self.assertRaisesRegex(
            ZenodoWorkflowError, "persistence failed"
        ):
            create_sandbox_remote_draft(
                deposit.pk, client
            )

        deposit.refresh_from_db()

        self.assertEqual(
            deposit.status, ZenodoDeposit.Status.UNKNOWN
        )
        self.assertIsNone(deposit.deposition_id)

    def test_unexpected_error_leaves_creating_state(self):
        from unittest.mock import Mock
        from identifiers.zenodo_workflow import (
            create_sandbox_remote_draft,
        )

        deposit = begin_sandbox_deposit(self.article.pk)
        client = Mock()

        client.create_draft.side_effect = RuntimeError(
            "Unexpected failure"
        )

        with self.assertRaises(RuntimeError):
            create_sandbox_remote_draft(
                deposit.pk, client
            )

        deposit.refresh_from_db()

        self.assertEqual(
            deposit.status, ZenodoDeposit.Status.CREATING
        )

    def test_invalid_draft_fields(self):
        from unittest.mock import Mock
        from identifiers.zenodo_sandbox import Draft
        from identifiers.zenodo_workflow import (
            create_sandbox_remote_draft,
        )

        cases = [
            Draft(
                0,
                "10.5072/zenodo.124",
                "https://sandbox.zenodo.org/api/files/test",
                "https://sandbox.zenodo.org/deposit/124",
            ),
            Draft(
                124,
                "invalid-doi",
                "https://sandbox.zenodo.org/api/files/test",
                "https://sandbox.zenodo.org/deposit/124",
            ),
            Draft(
                124,
                "10.5072/zenodo.124",
                "https://example.org/api/files/test",
                "https://sandbox.zenodo.org/deposit/124",
            ),
            Draft(
                124,
                "10.5072/zenodo.124",
                "https://sandbox.zenodo.org/api/files/test",
                "https://example.org/deposit/124",
            ),
        ]

        for draft in cases:
            with self.subTest(draft=draft):
                article = Article.objects.create(
                    title="Draft validation test"
                )

                deposit = ZenodoDeposit.objects.create(
                    article=article,
                    is_sandbox=True,
                    status=ZenodoDeposit.Status.READY,
                    metadata_snapshot=self.metadata,
                )

                client = Mock()
                client.create_draft.return_value = draft

                with self.assertRaises(ZenodoWorkflowError):
                    create_sandbox_remote_draft(
                        deposit.pk, client
                    )

                deposit.refresh_from_db()

                self.assertEqual(
                    deposit.status,
                    ZenodoDeposit.Status.UNKNOWN,
                )
                self.assertIsNone(deposit.deposition_id)
