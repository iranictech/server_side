"""Regression tests for Janeway reviewer invitation integration paths.

This module only exercises mocked assignment and notification dependencies.
It cannot send emails, create assignments, or affect production settings.
"""

from contextlib import ExitStack
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from django.core.exceptions import PermissionDenied
from django.forms import ValidationError
from django.test import override_settings

from review import forms, logic


def fake_setting(group, name, journal):
    if name == "default_review_form":
        return SimpleNamespace(processed_value=123)
    if name == "default_review_visibility":
        return SimpleNamespace(value="open")
    if name == "default_review_days":
        return SimpleNamespace(value="7")
    raise AssertionError("Unexpected setting: {}".format(name))


class InvitationCallSiteTests(TestCase):
    def test_standard_form_rejects_coi_block_as_form_validation(self):
        article = object()
        reviewer = object()
        form_state = SimpleNamespace(
            article=article, cleaned_data={"reviewer": reviewer}
        )

        with patch(
            "review.forms.enforce_reviewer_invitation_coi",
            side_effect=PermissionDenied("COI clearance required."),
        ) as guard:
            with self.assertRaises(ValidationError):
                forms.ReviewAssignmentForm.clean_reviewer(form_state)

        guard.assert_called_once_with(article, reviewer)

    def test_standard_form_accepts_reviewer_after_policy_check(self):
        article = object()
        reviewer = object()
        form_state = SimpleNamespace(
            article=article, cleaned_data={"reviewer": reviewer}
        )

        with patch("review.forms.enforce_reviewer_invitation_coi") as guard:
            result = forms.ReviewAssignmentForm.clean_reviewer(form_state)

        self.assertIs(result, reviewer)
        guard.assert_called_once_with(article, reviewer)

    def test_quick_assign_denial_precedes_assignment_and_notifications(self):
        reviewer = Mock()
        journal = Mock()
        journal.users_with_role.return_value = [reviewer]
        request = SimpleNamespace(journal=journal, user=Mock())
        article = Mock()

        with ExitStack() as stack:
            stack.enter_context(
                patch(
                    "review.logic.setting_handler.get_setting",
                    side_effect=fake_setting,
                )
            )
            stack.enter_context(patch("review.logic.models.ReviewForm.objects.get"))
            create = stack.enter_context(
                patch("review.logic.models.ReviewAssignment.objects.create")
            )
            events = stack.enter_context(
                patch("review.logic.event_logic.Events.raise_event")
            )
            notice = stack.enter_context(patch("review.logic.messages.add_message"))
            guard = stack.enter_context(
                patch(
                    "review.logic.enforce_reviewer_invitation_coi",
                    side_effect=PermissionDenied("COI clearance required."),
                )
            )
            result = logic.quick_assign(request, article, reviewer_user=reviewer)

        self.assertIsNone(result)
        guard.assert_called_once_with(article, reviewer)
        create.assert_not_called()
        events.assert_not_called()
        article.save.assert_not_called()
        notice.assert_called_once()

    @override_settings(REVIEWER_MATCHING_ENFORCE_COI_ON_INVITE=False)
    def test_quick_assign_legacy_behavior_with_policy_disabled(self):
        reviewer = Mock()
        journal = Mock()
        journal.users_with_role.return_value = [reviewer]
        request = SimpleNamespace(journal=journal, user=Mock())
        article = Mock()
        assignment = Mock()

        with ExitStack() as stack:
            stack.enter_context(
                patch(
                    "review.logic.setting_handler.get_setting",
                    side_effect=fake_setting,
                )
            )
            stack.enter_context(patch("review.logic.models.ReviewForm.objects.get"))
            create = stack.enter_context(
                patch(
                    "review.logic.models.ReviewAssignment.objects.create",
                    return_value=assignment,
                )
            )
            events = stack.enter_context(
                patch("review.logic.event_logic.Events.raise_event")
            )
            notify = stack.enter_context(
                patch(
                    "review.logic.get_reviewer_notification",
                    return_value="mock notification",
                )
            )
            result = logic.quick_assign(request, article, reviewer_user=reviewer)

        self.assertIs(result, assignment)
        self.assertEqual(create.call_count, 1)
        self.assertEqual(events.call_count, 2)
        article.save.assert_called_once()
        notify.assert_called_once()
