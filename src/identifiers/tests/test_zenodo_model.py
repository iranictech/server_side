from django.test import SimpleTestCase
from django.apps import apps
from django.db.models import PROTECT, ForeignKey


class ZenodoDepositModelTests(SimpleTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.model = apps.get_model(
            "identifiers",
            "ZenodoDeposit",
        )

    def test_model_is_registered(self):
        self.assertEqual(
            self.model._meta.db_table,
            "identifiers_zenododeposit",
        )

    def test_article_relationship(self):
        field = self.model._meta.get_field("article")

        self.assertIsInstance(field, ForeignKey)
        self.assertEqual(
            field.remote_field.model._meta.label,
            "submission.Article",
        )
        self.assertIs(
            field.remote_field.on_delete,
            PROTECT,
        )

    def test_sandbox_is_default(self):
        field = self.model._meta.get_field(
            "is_sandbox"
        )
        self.assertTrue(field.default)

    def test_default_status_is_ready(self):
        field = self.model._meta.get_field("status")
        self.assertEqual(field.default, "ready")

    def test_article_environment_unique_constraint(self):
        constraints = {
            c.name: c
            for c in self.model._meta.constraints
        }

        constraint = constraints[
            "unique_zenodo_article_env"
        ]

        self.assertEqual(
            tuple(constraint.fields),
            ("article", "is_sandbox"),
        )

    def test_remote_id_unique_constraint(self):
        constraints = {
            c.name: c
            for c in self.model._meta.constraints
        }

        constraint = constraints[
            "unique_zenodo_remote_id"
        ]

        self.assertEqual(
            tuple(constraint.fields),
            ("deposition_id", "is_sandbox"),
        )
        self.assertIsNotNone(constraint.condition)

    def test_reserved_and_published_doi_are_separate(self):
        fields = {
            field.name
            for field in self.model._meta.fields
        }

        self.assertIn("reserved_doi", fields)
        self.assertIn("published_doi", fields)
