from datetime import date

from django.conf import settings
from django.test import TestCase, override_settings

from core.models import Account, AccountRole, Role, XSLFile
from journal.models import Journal
from press.models import Press
from review.logic import get_reviewer_candidates
from review.models import ReviewAssignment, ReviewRound
from reviewer_matching.services import get_internal_matches
from submission.models import Article, STAGE_UNDER_REVIEW
from utils.install import update_settings


@override_settings(
    REVIEWER_MATCHING_ALLOW_EXTERNAL_REQUESTS=False,
    REVIEWER_MATCHING_ALLOW_ORCID_EMAIL_REQUESTS=False,
)
class NullReviewerORMTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        update_settings()

        XSLFile.objects.get_or_create(
            label=settings.DEFAULT_XSL_FILE_LABEL,
            defaults={
                "file": "null-reviewer-test.xsl",
                "original_filename": "null-reviewer-test.xsl",
            },
        )

        Press.objects.create(
            name="Null Reviewer Test Press",
            domain="nullreviewpress.testserver",
        )

        journal = Journal.objects.create(
            code="nrt",
            domain="nullreview.testserver",
        )

        cls.article = Article.objects.create(
            journal=journal,
            title="Null reviewer regression article",
            stage=STAGE_UNDER_REVIEW,
        )

        review_round = ReviewRound.objects.create(
            article=cls.article,
            round_number=1,
        )

        role, _ = Role.objects.get_or_create(
            slug="reviewer",
            defaults={"name": "Reviewer"},
        )

        def create_reviewer(username):
            account = Account.objects.create(
                username=username,
                email=f"{username}@example.org",
                first_name=username,
                last_name="Test",
                is_active=True,
            )

            AccountRole.objects.create(
                user=account,
                journal=journal,
                role=role,
            )

            return account

        assigned = create_reviewer("nulltest_assigned")
        cls.available = create_reviewer("nulltest_available")

        for reviewer in (None, assigned):
            ReviewAssignment.objects.create(
                article=cls.article,
                review_round=review_round,
                reviewer=reviewer,
                date_due=date.today(),
            )

    def test_null_reviewer_is_ignored(self):
        candidates = set(
            get_reviewer_candidates(self.article)
            .values_list("pk", flat=True)
        )

        self.assertEqual(
            candidates,
            {self.available.pk},
        )

        matches = get_internal_matches(
            self.article,
            editor=None,
        )

        self.assertEqual(
            [item["account_id"] for item in matches],
            [self.available.pk],
        )
