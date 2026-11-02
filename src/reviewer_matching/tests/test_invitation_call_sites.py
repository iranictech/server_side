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


    @override_settings(REVIEWER_MATCHING_ENFORCE_COI_ON_INVITE=True)
    def test_review_invitation_events_deny_before_subscribers(self):
        from django.core.exceptions import PermissionDenied

        from events.logic import Events

        assignment = SimpleNamespace(article=object(), reviewer=object())
        events = (
            Events.ON_REVIEWER_REQUESTED,
            Events.ON_REVIEWER_REQUESTED_NOTIFICATION,
            Events.ON_REVIEWER_REQUESTED_ACKNOWLEDGE,
        )
        for event in events:
            with self.subTest(event=event):
                subscriber = Mock()
                with patch.object(Events, "_hooks", {event: [subscriber]}):
                    with patch(
                        "reviewer_matching.invitation_policy."
                        "enforce_reviewer_invitation_coi",
                        side_effect=PermissionDenied("COI review required."),
                    ) as gate:
                        with self.assertRaises(PermissionDenied):
                            Events.raise_event(event, review_assignment=assignment)

                gate.assert_called_once_with(assignment.article, assignment.reviewer)
                subscriber.assert_not_called()

    @override_settings(REVIEWER_MATCHING_ENFORCE_COI_ON_INVITE=True)
    def test_event_gate_rejects_missing_assignment_without_dispatch(self):
        from django.core.exceptions import PermissionDenied

        from events.logic import Events

        event = Events.ON_REVIEWER_REQUESTED_ACKNOWLEDGE
        subscriber = Mock()
        with patch.object(Events, "_hooks", {event: [subscriber]}):
            with self.assertRaises(PermissionDenied):
                Events.raise_event(event)
        subscriber.assert_not_called()

    @override_settings(REVIEWER_MATCHING_ENFORCE_COI_ON_INVITE=True)
    def test_event_gate_allows_approved_review_invitation(self):
        from events.logic import Events

        assignment = SimpleNamespace(article=object(), reviewer=object())
        event = Events.ON_REVIEWER_REQUESTED_NOTIFICATION
        subscriber = Mock()
        with patch.object(Events, "_hooks", {event: [subscriber]}):
            with patch(
                "reviewer_matching.invitation_policy."
                "enforce_reviewer_invitation_coi"
            ) as gate:
                Events.raise_event(event, review_assignment=assignment)

        gate.assert_called_once_with(assignment.article, assignment.reviewer)
        subscriber.assert_called_once_with(review_assignment=assignment)

    @override_settings(REVIEWER_MATCHING_ENFORCE_COI_ON_INVITE=False)
    def test_event_gate_disabled_preserves_legacy_dispatch(self):
        from events.logic import Events

        event = Events.ON_REVIEWER_REQUESTED_ACKNOWLEDGE
        subscriber = Mock()
        with patch.object(Events, "_hooks", {event: [subscriber]}):
            with patch(
                "reviewer_matching.invitation_policy."
                "enforce_reviewer_invitation_coi"
            ) as gate:
                Events.raise_event(event, sample="legacy")

        gate.assert_not_called()
        subscriber.assert_called_once_with(sample="legacy")

    def test_request_reminder_gate_blocks_before_outbound_email(self):
        from django.core.exceptions import PermissionDenied

        article = object()
        reviewer = Mock()
        assignment = SimpleNamespace(article=article, reviewer=reviewer)
        form = SimpleNamespace(
            cleaned_data={"subject": "Reminder", "body": "Please review"}
        )
        request = SimpleNamespace(user=Mock())

        with patch(
            "review.logic.enforce_reviewer_invitation_coi",
            side_effect=PermissionDenied("COI review required."),
        ) as gate:
            with patch(
                "review.logic.notify_helpers.send_email_with_body_from_user"
            ) as mail:
                with self.assertRaises(PermissionDenied):
                    logic.send_review_reminder(request, form, assignment, "request")

        gate.assert_called_once_with(article, reviewer)
        mail.assert_not_called()

    def test_accepted_review_reminder_is_not_a_new_invitation(self):
        reviewer = Mock()
        reviewer.full_name.return_value = "Reviewer"
        assignment = SimpleNamespace(article=object(), reviewer=reviewer)
        form = SimpleNamespace(cleaned_data={"subject": "Status", "body": "Reminder"})
        request = SimpleNamespace(user=Mock())

        with patch("review.logic.enforce_reviewer_invitation_coi") as gate:
            with patch(
                "review.logic.notify_helpers.send_email_with_body_from_user"
            ) as mail:
                logic.send_review_reminder(request, form, assignment, "accepted")

        gate.assert_not_called()
        mail.assert_called_once()
