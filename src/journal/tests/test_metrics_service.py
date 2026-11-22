"""Regression tests for per-journal metrics (isolated Django test database)."""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from journal.metrics_service import refresh_metrics
from journal.models import Issue, IssueType, JournalMetrics
from review.models import ReviewAssignment
from submission.models import STAGE_PUBLISHED, STAGE_REJECTED
from utils.testing import helpers


class JournalMetricsServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        helpers.create_press()
        cls.journal_one, cls.journal_two = helpers.create_journals()

    def _article(self, journal, **kwargs):
        return helpers.create_article(journal, **kwargs)

    def test_empty_journal_has_no_fabricated_rates(self):
        result = refresh_metrics(self.journal_one)
        self.assertEqual(result.submitted_count, 0)
        self.assertEqual(result.accepted_count, 0)
        self.assertEqual(result.rejected_count, 0)
        self.assertEqual(result.completed_reviews_count, 0)
        self.assertIsNone(result.acceptance_rate)
        self.assertIsNone(result.average_review_days)
        self.assertIsNotNone(result.calculated_at)

    def test_acceptance_rate_and_journal_isolation(self):
        now = timezone.now()
        self._article(
            self.journal_one,
            stage=STAGE_PUBLISHED,
            date_submitted=now - timedelta(days=70),
            date_accepted=now - timedelta(days=10),
            date_published=now - timedelta(days=8),
        )
        self._article(
            self.journal_one,
            stage=STAGE_REJECTED,
            date_submitted=now - timedelta(days=50),
            date_declined=now - timedelta(days=9),
        )
        # Imported article is not included in the submission/decision workflow.
        self._article(
            self.journal_one,
            is_import=True,
            date_submitted=now - timedelta(days=30),
            date_accepted=now - timedelta(days=7),
        )
        self._article(
            self.journal_two,
            date_submitted=now - timedelta(days=20),
            date_accepted=now - timedelta(days=4),
        )
        first = refresh_metrics(self.journal_one)
        second = refresh_metrics(self.journal_two)
        self.assertEqual(first.submitted_count, 2)
        self.assertEqual(first.accepted_count, 1)
        self.assertEqual(first.rejected_count, 1)
        self.assertEqual(first.published_count, 1)
        self.assertEqual(first.acceptance_rate, Decimal('50.00'))
        self.assertEqual(second.accepted_count, 1)
        self.assertEqual(second.rejected_count, 0)
        self.assertEqual(second.acceptance_rate, Decimal('100.00'))
        self.assertNotEqual(first.pk, second.pk)

    def test_review_average_uses_only_valid_completed_assignments(self):
        now = timezone.now()
        article = self._article(
            self.journal_one,
            date_submitted=now - timedelta(days=30),
        )
        base = dict(article=article, date_due=timezone.localdate())
        ReviewAssignment.objects.create(
            **base,
            date_accepted=now - timedelta(days=6),
            date_complete=now - timedelta(days=4),
            decision='accept',
            is_complete=True,
        )
        ReviewAssignment.objects.create(
            **base,
            date_accepted=now - timedelta(days=10),
            date_complete=now - timedelta(days=6),
            decision='reject',
            is_complete=True,
        )
        ReviewAssignment.objects.create(
            **base,
            date_accepted=now - timedelta(days=10),
            date_complete=now - timedelta(days=1),
            decision='withdrawn',
            is_complete=True,
        )
        ReviewAssignment.objects.create(
            **base,
            date_accepted=now - timedelta(days=10),
            date_complete=now - timedelta(days=1),
            decision='accept',
            is_complete=False,
        )
        result = refresh_metrics(self.journal_one)
        self.assertEqual(result.completed_reviews_count, 2)
        self.assertEqual(result.average_review_days, Decimal('3.00'))

    def test_policy_fields_survive_refresh(self):
        item = JournalMetrics.objects.create(
            journal=self.journal_one,
            review_target_days=10,
            issues_per_year=4,
            apc_policy='free',
            manual_acceptance_rate=Decimal('25.00'),
            manual_source='Historical editorial report',
        )
        refresh_metrics(self.journal_one)
        item.refresh_from_db()
        self.assertEqual(item.review_target_days, 10)
        self.assertEqual(item.issues_per_year, 4)
        self.assertEqual(item.apc_policy, 'free')
        self.assertEqual(item.manual_acceptance_rate, Decimal('25.00'))
        self.assertEqual(item.manual_source, 'Historical editorial report')
        self.assertIsNone(item.acceptance_rate)

    def test_regular_issues_are_counted_but_collections_are_not(self):
        now = timezone.now()
        normal = IssueType.objects.get(journal=self.journal_one, code='issue')
        collection = IssueType.objects.get(journal=self.journal_one, code='collection')
        Issue.objects.create(
            journal=self.journal_one,
            issue_type=normal,
            issue='1',
            date=now - timedelta(days=10),
        )
        Issue.objects.create(
            journal=self.journal_one,
            issue_type=collection,
            issue='special',
            date=now - timedelta(days=10),
        )
        result = refresh_metrics(self.journal_one)
        self.assertEqual(result.published_issues_count, 1)
