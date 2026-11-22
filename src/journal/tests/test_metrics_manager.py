"""Permission, manager form, and refresh tests for Journal Metrics."""
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.test import RequestFactory, TestCase

from journal.metrics_forms import JournalMetricsForm
from journal.metrics_views import journal_metrics_manager
from journal.models import JournalMetrics
from utils.testing import helpers


class JournalMetricsManagerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        helpers.create_press()
        cls.journal_one, cls.journal_two = helpers.create_journals()
        cls.manager_one = helpers.create_user(
            "metrics-manager-1@example.com",
            roles=["journal-manager"], journal=cls.journal_one,
        )
        cls.manager_two = helpers.create_user(
            "metrics-manager-2@example.com",
            roles=["journal-manager"], journal=cls.journal_two,
        )

        # Test users must be active to pass Janeway authentication.
        for manager in (cls.manager_one, cls.manager_two):
            manager.is_active = True
            manager.save(update_fields=["is_active"])

    def _request(self, journal, user, action=None, **data):
        factory = RequestFactory()
        if action is None:
            request = factory.get("/manager/metrics/")
        else:
            request = factory.post("/manager/metrics/", {"action": action, **data})
        request.journal = journal
        request.user = user
        return request

    @patch("journal.metrics_views.render", return_value=HttpResponse("OK"))
    def test_manager_can_view_own_journal(self, mocked_render):
        response = journal_metrics_manager(
            self._request(self.journal_one, self.manager_one)
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(mocked_render.call_args[0][2]["journal"], self.journal_one)
        self.assertFalse(JournalMetrics.objects.filter(journal=self.journal_one).exists())

    def test_manager_cannot_access_another_journal(self):
        with self.assertRaises(PermissionDenied):
            journal_metrics_manager(self._request(self.journal_one, self.manager_two))
        self.assertFalse(JournalMetrics.objects.exists())

    def test_press_context_not_allowed(self):
        with self.assertRaises(Http404):
            journal_metrics_manager(self._request(None, self.manager_one))

    def test_fallback_needs_a_source(self):
        form = JournalMetricsForm(data={
            "open_access_policy": "unknown", "apc_policy": "unknown",
            "manual_review_days": "10", "manual_source": "",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("manual_source", form.errors)

    def test_free_apc_cannot_have_positive_amount(self):
        form = JournalMetricsForm(data={
            "open_access_policy": "open", "apc_policy": "free",
            "apc_amount": "100", "apc_currency": "USD",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("apc_policy", form.errors)

    @patch("journal.metrics_views.messages.success")
    def test_policy_save_is_journal_specific(self, mocked_messages):
        request = self._request(
            self.journal_one, self.manager_one, "save",
            review_target_days="10", issues_per_year="4",
            open_access_policy="open", apc_policy="free",
            apc_amount="", apc_currency="",
            manual_acceptance_rate="", manual_review_days="", manual_source="",
        )
        response = journal_metrics_manager(request)
        self.assertEqual(response.status_code, 302)
        row = JournalMetrics.objects.get(journal=self.journal_one)
        self.assertEqual(row.review_target_days, 10)
        self.assertEqual(row.issues_per_year, 4)
        self.assertEqual(row.apc_policy, "free")
        self.assertFalse(JournalMetrics.objects.filter(journal=self.journal_two).exists())

    @patch("journal.metrics_views.messages.success")
    def test_refresh_preserves_policy_values(self, mocked_messages):
        JournalMetrics.objects.create(
            journal=self.journal_one,
            review_target_days=10,
            issues_per_year=4,
            apc_policy="free",
        )
        response = journal_metrics_manager(
            self._request(self.journal_one, self.manager_one, "refresh")
        )
        self.assertEqual(response.status_code, 302)
        row = JournalMetrics.objects.get(journal=self.journal_one)
        self.assertIsNotNone(row.calculated_at)
        self.assertEqual(row.review_target_days, 10)
        self.assertEqual(row.issues_per_year, 4)
        self.assertEqual(row.apc_policy, "free")
        self.assertFalse(JournalMetrics.objects.filter(journal=self.journal_two).exists())
