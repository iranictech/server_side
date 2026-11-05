from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch, sentinel

from django.test import SimpleTestCase

from review.logic import get_reviewer_candidates


class ReviewerCandidateNullSafetyTests(SimpleTestCase):

    def test_null_assignment_is_ignored_and_exclusions_preserved(self):
        current_round = object()

        article = Mock()
        article.current_review_round_object.return_value = current_round
        article.journal.users_with_role.return_value = sentinel.reviewers

        assignments = MagicMock()

        # Simulate an assignment with no reviewer,
        # followed by an assignment with reviewer ID 41.
        assignments.__iter__.return_value = iter([
            SimpleNamespace(reviewer=None),
            SimpleNamespace(
                reviewer=SimpleNamespace(pk=41)
            ),
        ])

        assignments.values_list.return_value = [41]

        article.reviewassignment_set.filter.return_value = assignments

        editor = SimpleNamespace(pk=99)
        extra_exclusions = [SimpleNamespace(pk=77)]

        with patch(
            "review.logic.get_reviewers",
            return_value=sentinel.result,
        ) as mocked_get_reviewers:

            result = get_reviewer_candidates(
                article,
                user=editor,
                reviewers_to_exclude=extra_exclusions,
            )

        self.assertIs(result, sentinel.result)

        article.reviewassignment_set.filter.assert_called_once_with(
            review_round=current_round,
            reviewer_id__isnull=False,
        )

        assignments.values_list.assert_called_once_with(
            "reviewer_id",
            flat=True,
        )

        mocked_get_reviewers.assert_called_once_with(
            article,
            sentinel.reviewers,
            [41, 99, 77],
        )
