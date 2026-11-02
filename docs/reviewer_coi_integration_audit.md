# Reviewer COI invitation-path audit (development branch)

Scope: native Janeway reviewer assignment/request flows in `src/review/`,
the `events` dispatcher and native email callbacks. This is a code-level
audit, not a production deployment or complete assessment of third-party plugins.

## Current safeguards (default OFF)

The strict policy is controlled by
`REVIEWER_MATCHING_ENFORCE_COI_ON_INVITE` (default `False`).

| Path | Control when strict policy is enabled |
| --- | --- |
| Standard `ReviewAssignmentForm` | Re-check before saving |
| `review.logic.quick_assign` | Check before assignment/events |
| `review.views.notify_reviewer` | Check before notification |
| Bulk CSV `process_reviewer_csv` | Disabled before any row processing |
| `Events.raise_event` for three reviewer-request events | Check before subscribers, even if invoked directly |
| `review.logic.send_review_reminder`, type `request` | Check before sending mail |
| Reminder of an already accepted review | Not treated as a new invitation |

The three guarded events are `ON_REVIEWER_REQUESTED`,
`ON_REVIEWER_REQUESTED_NOTIFICATION`, and
`ON_REVIEWER_REQUESTED_ACKNOWLEDGE`.

## Limitations and follow-up work

- This gate does **not** prevent a direct `ReviewAssignment.objects.create`
  from custom code. It protects the audited entry points and event
  dispatch, not arbitrary ORM writes.
- A plugin that sends mail directly, without these events or native views,
  requires separate review. An event guard is not an SMTP-wide policy.
- Permission and eligibility can change after an editorial COI decision.
  The policy rechecks account activity and manuscript authorship at use time,
  but a complete institution/financial/relationship review remains human.
- Bulk CSV is intentionally unavailable in strict mode; a staged preflight
  workflow is needed before re-enabling it.
- The feature flag must not be activated in Production until a separate
  Staging rollout, integration audit and migration review are approved.

## Verification

Run the full repository CI matrix and the dedicated
`reviewer_matching.tests.test_invitation_call_sites` test suite.
