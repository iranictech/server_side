from django.db import connection
from django.test import TestCase

from core.models import Account
from journal.models import Journal
from submission.models import Article


class ReviewerMatchingDatabaseSmokeTests(TestCase):
    """Ensure the test schema supports Janeway's core models."""

    def test_models_can_be_queried(self):
        self.assertEqual(connection.vendor, "sqlite")

        tables = set(connection.introspection.table_names())

        models = (Account, Journal, Article)

        for model in models:
            with self.subTest(model=model.__name__):
                self.assertIn(model._meta.db_table, tables)

                # Actual ORM query against the test database.
                count = model.objects.count()

                self.assertIsInstance(count, int)

    def test_database_is_not_production(self):
        self.assertEqual(connection.vendor, "sqlite")

        actual = str(connection.settings_dict["NAME"])

        # The Django SQLite test runner normally uses an
        # in-memory test database rather than the development DB.
        self.assertIn("memory", actual.lower())
