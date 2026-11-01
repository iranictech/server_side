"""Access policy equivalent to Janeway's Assign Reviewer eligibility.

The existing editor_user_required decorator checks the role and
article-level Section Editor assignment before this policy runs.
This function enforces the remaining assignment conditions.
"""

from django.core.exceptions import PermissionDenied

from submission.models import REVIEW_STAGES, STAGE_ACCEPTED


def enforce_assign_reviewer_policy(request, article):
    if request.user in article.author_accounts:
        if not article.editor_override(request.user):
            raise PermissionDenied(
                "Article author requires an EditorOverride."
            )

    allowed_stages = REVIEW_STAGES.copy()
    allowed_stages.remove(STAGE_ACCEPTED)

    if article.stage not in allowed_stages:
        raise PermissionDenied(
            "Reviewer assignment is not allowed at this stage."
        )
