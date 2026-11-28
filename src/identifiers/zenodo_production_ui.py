"""
Zenodo Production UI.

POST-only operations.
Independent authorization.
Publication is disabled.
"""

from django.conf import settings
from django.contrib import messages
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect

from security.decorators import (
    production_user_or_editor_required,
)

from submission.models import Article
from identifiers.zenodo_models import ZenodoDeposit

from identifiers.zenodo_production_permissions import (
    can_operate_zenodo_production,
    is_production_article_allowed,
)

from identifiers.zenodo_production_metadata import (
    prepare_production_deposit,
    check_production_eligibility,
)

from identifiers.zenodo_production_workflow import (
    create_production_draft,
    upload_production_pdf,
    reconcile_production_pdf,
)

from identifiers.zenodo_production import (
    ZenodoProductionClient,
)


from identifiers.zenodo_production_publish import (
    publish_production_deposit,
    reconcile_production_publication,
    PUBLISH_PENDING,
)


def can_view_production_panel(request, article):
    return bool(
        getattr(
            settings,
            "ZENODO_PRODUCTION_UI_ENABLED",
            False,
        )
        and request.user.is_authenticated
        and request.user.is_active
        and request.user.is_superuser
        and request.user.pk in getattr(
            settings,
            "ZENODO_PRODUCTION_ALLOWED_USERS",
            (),
        )
        and request.journal
        and article.journal_id == request.journal.pk
        and is_production_article_allowed(article)
    )


def production_panel_context(request, article):

    visible = can_view_production_panel(
        request, article
    )

    if not visible:
        return {
            "zenodo_production_visible": False,
        }

    deposit = ZenodoDeposit.objects.filter(
        article=article,
        is_sandbox=False,
    ).first()

    eligibility = check_production_eligibility(
        article,
        check_existing=False,
    )

    return {
        "zenodo_production_visible": True,
        "zenodo_production_publish_enabled": getattr(
            settings,
            "ZENODO_PRODUCTION_PUBLISH_ENABLED",
            False,
        ),
        "zenodo_publication_pending": bool(
            deposit and deposit.last_error == PUBLISH_PENDING
        ),
        "zenodo_production_deposit": deposit,
        "zenodo_production_eligibility": eligibility,
        "zenodo_production_can_operate":
            can_operate_zenodo_production(
                request, article
            ),
    }


@require_POST
@csrf_protect
@production_user_or_editor_required
def zenodo_production_action(
    request, article_id, action
):

    article = get_object_or_404(
        Article,
        pk=article_id,
        journal=request.journal,
    )

    if (
        not can_view_production_panel(request, article)
        or not can_operate_zenodo_production(
            request, article
        )
    ):
        return HttpResponseForbidden(
            "Production operation not permitted"
        )

    if action not in (
        "prepare",
        "create",
        "upload",
        "check",
        "reconcile",
        "publish",
        "reconcile_publish",
    ):
        return HttpResponseForbidden(
            "Unsupported Production action"
        )

    if action != "check":
        if request.POST.get("confirm") != "yes":
            return HttpResponseForbidden(
                "Explicit confirmation required"
            )

    destination = reverse(
        "article_identifiers",
        kwargs={"article_id": article.pk},
    )

    deposit = ZenodoDeposit.objects.filter(
        article=article,
        is_sandbox=False,
    ).first()

    try:

        if action == "prepare":

            if deposit is not None:
                messages.warning(
                    request,
                    "Production deposit already exists.",
                )
                return redirect(destination)

            prepare_production_deposit(
                article.pk,
                confirmed=True,
            )

            messages.success(
                request,
                "Production deposit prepared locally.",
            )

            return redirect(destination)

        if deposit is None:
            messages.error(
                request,
                "Prepare Production deposit first.",
            )
            return redirect(destination)

        client = ZenodoProductionClient()

        if action == "create":

            create_production_draft(
                deposit.pk,
                client,
                confirmed=True,
            )

            messages.success(
                request,
                "Production draft created.",
            )

        elif action == "upload":

            upload_production_pdf(
                deposit.pk,
                client,
                confirmed=True,
            )

            messages.success(
                request,
                "Production PDF upload verified.",
            )

        elif action == "reconcile":

            reconcile_production_pdf(
                deposit.pk,
                client,
                confirmed=True,
            )

            messages.success(
                request,
                "Production PDF reconciled.",
            )

        elif action == "publish":
            publish_production_deposit(
                deposit.pk,
                client,
                confirmed=True,
            )
            messages.success(
                request,
                "Publication verified. DOI synchronized.",
            )

        elif action == "reconcile_publish":
            reconcile_production_publication(
                deposit.pk,
                client,
                confirmed=True,
            )
            messages.success(
                request,
                "Publication reconciled. DOI synchronized.",
            )

        elif action == "check":

            if not deposit.deposition_id:
                messages.warning(
                    request,
                    "Remote deposit ID is unavailable.",
                )
                return redirect(destination)

            remote = client.get_deposition(
                deposit.deposition_id
            )

            if remote.get("id") != deposit.deposition_id:
                raise ValueError(
                    "Remote deposit identity mismatch"
                )

            messages.info(
                request,
                "Production remote deposit checked. "
                "Remote ID: {}".format(
                    deposit.deposition_id
                ),
            )

    except Exception:

        messages.error(
            request,
            "Production operation could not be confirmed. "
            "Review the current state before continuing.",
        )

    return redirect(destination)
