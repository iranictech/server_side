"""
Sandbox-only Zenodo actions for Janeway article identifiers.

All actions are POST-only and disabled by default.
No publication endpoint is exposed.
"""

from django.conf import settings
from django.contrib import messages
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from security.decorators import production_user_or_editor_required
from submission.models import Article
from identifiers.zenodo_models import ZenodoDeposit


@require_POST
@production_user_or_editor_required
def zenodo_action(request, article_id, action):
    article = get_object_or_404(
        Article,
        pk=article_id,
        journal=request.journal,
    )

    destination = reverse(
        "article_identifiers",
        kwargs={"article_id": article.pk},
    )

    # Separate authorization from the existing editor decorator.
    if not request.user.is_authenticated or not request.user.is_superuser:
        return HttpResponseForbidden("Zenodo operation not permitted")

    if not getattr(settings, "ZENODO_SANDBOX_UI_ENABLED", False):
        return HttpResponseForbidden("Zenodo operations are disabled")

    deposit = ZenodoDeposit.objects.filter(
        article=article,
        is_sandbox=True,
    ).first()

    if action == "prepare":
        if deposit is not None:
            messages.warning(request, "Sandbox deposit already exists.")
            return redirect(destination)

        from identifiers.zenodo_workflow import begin_sandbox_deposit

        try:
            begin_sandbox_deposit(article.pk)
            messages.success(request, "Local Sandbox deposit prepared.")
        except Exception:
            messages.error(request, "Sandbox preparation failed.")

        return redirect(destination)

    if deposit is None:
        messages.error(request, "Prepare the Sandbox deposit first.")
        return redirect(destination)

    # Remote operations require the token to be configured on the server.
    from identifiers.zenodo_sandbox import ZenodoSandboxClient

    try:
        client = ZenodoSandboxClient()

        if action == "create":
            from identifiers.zenodo_workflow import (
                create_sandbox_remote_draft,
            )
            create_sandbox_remote_draft(deposit.pk, client)
            messages.success(request, "Sandbox draft creation completed.")

        elif action == "upload":
            from identifiers.zenodo_upload_workflow import (
                upload_sandbox_article_pdf,
            )
            upload_sandbox_article_pdf(deposit.pk, client)
            messages.success(request, "Sandbox PDF upload verified.")

        elif action == "check":
            from identifiers.zenodo_recovery import (
                inspect_known_sandbox_deposit,
            )
            result = inspect_known_sandbox_deposit(
                deposit.pk, client
            )
            messages.info(
                request,
                "Remote deposit checked. Remote ID: {}".format(
                    result["remote_deposition_id"]
                ),
            )

        elif action == "reconcile":
            if request.POST.get("confirm") != "yes":
                return HttpResponseForbidden(
                    "Explicit reconciliation confirmation required"
                )

            from identifiers.zenodo_upload_reconcile import (
                reconcile_sandbox_pdf_upload,
            )

            result = reconcile_sandbox_pdf_upload(
                deposit.pk,
                client,
                confirmed=True,
            )

            if result["changed"]:
                messages.success(
                    request,
                    "Sandbox PDF upload reconciled.",
                )
            else:
                messages.warning(
                    request,
                    "Reconciliation did not change the deposit.",
                )

        else:
            return HttpResponseForbidden("Unsupported Zenodo action")

    except Exception:
        # Never expose HTTP response bodies, tokens or remote exceptions.
        messages.error(
            request,
            "Zenodo operation could not be confirmed. "
            "Review the deposit status before any further action.",
        )

    return redirect(destination)
