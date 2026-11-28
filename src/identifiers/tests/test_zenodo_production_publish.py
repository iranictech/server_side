from unittest.mock import patch

from django.test import TestCase

from identifiers.models import Identifier
from identifiers.zenodo_models import ZenodoDeposit
from identifiers.zenodo_production_publish import (
    _finalize,
    PUBLISH_PENDING,
)
from identifiers.zenodo_production_workflow import (
    ProductionWorkflowError,
)
from identifiers.logic import crossref_blocked_article_ids
from submission.models import Article


class ZenodoProductionPublishTests(TestCase):

    def setUp(self):
        self.article = Article.objects.create(
            title="Publication verification test"
        )

        self.doi = "10.5281/zenodo.999999999"

        self.deposit = ZenodoDeposit.objects.create(
            article=self.article,
            is_sandbox=False,
            status=ZenodoDeposit.Status.UNKNOWN,
            deposition_id=999999999,
            reserved_doi=self.doi,
            last_error=PUBLISH_PENDING,
            metadata_snapshot={"prereserve_doi": True},
        )

        self.remote = {
            "id": self.deposit.deposition_id,
            "submitted": True,
            "state": "done",
            "doi": self.doi,
        }

    @patch(
        "identifiers.zenodo_production_publish._verify_pdf"
    )
    @patch(
        "identifiers.zenodo_production_publish._verify_metadata"
    )
    def test_new_doi_is_saved(self, metadata, pdf):
        result = _finalize(
            self.deposit.pk,
            self.remote,
        )

        identifier = Identifier.objects.get(
            article=self.article,
            id_type="doi",
        )

        self.assertEqual(identifier.identifier, self.doi)
        self.assertEqual(identifier.doi_provider, "zenodo")
        self.assertEqual(
            result.status,
            ZenodoDeposit.Status.PUBLISHED,
        )

        self.assertIn(
            self.article.pk,
            crossref_blocked_article_ids(
                [self.article.pk]
            ),
        )

        with self.assertRaises(ProductionWorkflowError):
            _finalize(self.deposit.pk, self.remote)

        self.assertEqual(
            Identifier.objects.filter(
                article=self.article,
                id_type="doi",
            ).count(),
            1,
        )

    @patch(
        "identifiers.zenodo_production_publish._verify_pdf"
    )
    @patch(
        "identifiers.zenodo_production_publish._verify_metadata"
    )
    def test_existing_crossref_doi_is_preserved(
        self, metadata, pdf
    ):
        doi = "10.12345/example-test"

        identifier = Identifier.objects.create(
            article=self.article,
            id_type="doi",
            identifier=doi,
            doi_provider="crossref",
        )

        self.deposit.metadata_snapshot = {"doi": doi}
        self.deposit.reserved_doi = doi
        self.deposit.save()

        self.remote["doi"] = doi

        _finalize(self.deposit.pk, self.remote)

        identifier.refresh_from_db()

        self.assertEqual(identifier.identifier, doi)
        self.assertEqual(
            identifier.doi_provider, "crossref"
        )
        self.assertEqual(
            Identifier.objects.filter(
                article=self.article,
                id_type="doi",
            ).count(),
            1,
        )
        self.assertNotIn(
            self.article.pk,
            crossref_blocked_article_ids(
                [self.article.pk]
            ),
        )

    def test_unconfirmed_publication_is_blocked(self):
        self.remote["submitted"] = False

        with self.assertRaises(ProductionWorkflowError):
            _finalize(self.deposit.pk, self.remote)

        self.assertFalse(
            Identifier.objects.filter(
                article=self.article,
                id_type="doi",
            ).exists()
        )

        self.deposit.refresh_from_db()

        self.assertEqual(
            self.deposit.status,
            ZenodoDeposit.Status.UNKNOWN,
        )

    def test_pending_zenodo_blocks_crossref(self):
        self.assertIn(
            self.article.pk,
            crossref_blocked_article_ids(
                [self.article.pk]
            ),
        )

    def test_sandbox_does_not_block_crossref(self):
        self.deposit.is_sandbox = True
        self.deposit.save()

        self.assertNotIn(
            self.article.pk,
            crossref_blocked_article_ids(
                [self.article.pk]
            ),
        )
