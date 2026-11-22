"""Refresh a journal's measured metrics without changing editor-set policies."""

from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Avg, DurationField, ExpressionWrapper, F, Q
from django.utils import timezone

from journal.models import Issue, JournalMetrics
from review.models import ReviewAssignment
from submission.models import Article, STAGE_PUBLISHED


QUANTIZE = Decimal("0.01")


def _days(duration):
    if duration is None:
        return None
    return (Decimal(str(duration.total_seconds())) / Decimal(86400)).quantize(
        QUANTIZE, rounding=ROUND_HALF_UP
    )


def refresh_metrics(journal):
    """Recalculate rolling-365-day statistics and persist one journal row.

    The manager's targets, policy settings and manual fallback values
    are never updated here. No automatic results are invented when a
    denominator/sample is zero.
    """
    now = timezone.now()
    cutoff = now - timedelta(days=365)

    # Ignore imported manuscripts when measuring submission/decision workflow.
    submissions = Article.objects.filter(
        journal=journal, is_import=False, date_submitted__isnull=False
    )
    submitted = submissions.filter(date_submitted__gte=cutoff).count()
    accepted = submissions.filter(
        date_accepted__gte=cutoff, date_accepted__lte=now
    ).exclude(stage__in=["preprint_review", "preprint_published"]).count()
    rejected = submissions.filter(
        date_declined__gte=cutoff, date_declined__lte=now
    ).count()
    decisions = accepted + rejected
    rate = (
        (Decimal(accepted) * 100 / Decimal(decisions)).quantize(
            QUANTIZE, rounding=ROUND_HALF_UP
        )
        if decisions
        else None
    )

    published = Article.objects.filter(
        journal=journal,
        stage=STAGE_PUBLISHED,
        date_published__gte=cutoff,
        date_published__lte=now,
    ).count()

    published_issues = Issue.objects.filter(
        journal=journal,
        date__gte=cutoff,
        date__lte=now,
    ).filter(
        Q(issue_type__code="issue")
        | Q(issue_type__isnull=True, old_issue_type="Issue")
    ).count()

    # Time spent writing a completed reviewer report, not first-decision time.
    completed = ReviewAssignment.objects.filter(
        article__journal=journal,
        is_complete=True,
        date_accepted__isnull=False,
        date_complete__gte=cutoff,
        date_complete__lte=now,
        date_declined__isnull=True,
        decision__isnull=False,
    ).filter(
        date_complete__gte=F("date_accepted"),
    ).exclude(decision__in=("", "withdrawn", "cancelled"))

    avg_duration = completed.aggregate(
        value=Avg(
            ExpressionWrapper(
                F("date_complete") - F("date_accepted"),
                output_field=DurationField(),
            )
        )
    )["value"]
    completed_count = completed.count()

    metrics, _created = JournalMetrics.objects.get_or_create(journal=journal)
    metrics.submitted_count = submitted
    metrics.accepted_count = accepted
    metrics.rejected_count = rejected
    metrics.published_count = published
    metrics.published_issues_count = published_issues
    metrics.completed_reviews_count = completed_count
    metrics.acceptance_rate = rate
    metrics.average_review_days = _days(avg_duration)
    metrics.calculated_at = now
    metrics.save(update_fields=[
        "submitted_count", "accepted_count", "rejected_count",
        "published_count", "published_issues_count", "completed_reviews_count",
        "acceptance_rate", "average_review_days", "calculated_at", "updated_at",
    ])
    return metrics
