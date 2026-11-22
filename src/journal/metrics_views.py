"""Per-journal metrics manager (uses Janeway's existing staff roles)."""
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from journal.metrics_forms import JournalMetricsForm
from journal.metrics_service import refresh_metrics
from journal.models import JournalMetrics
from security.decorators import base_check_required


@base_check_required
@require_http_methods(["GET", "POST"])
def journal_metrics_manager(request):
    journal = getattr(request, "journal", None)
    if journal is None:
        raise Http404("Journal is required.")
    if not (
        request.user.is_staff
        or request.user.is_journal_manager(journal)
        or request.user.has_senior_editor_role(request)
    ):
        raise PermissionDenied("Only journal managers and senior editors may manage metrics.")

    metrics = JournalMetrics.objects.filter(journal=journal).first()
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "refresh":
            refresh_metrics(journal)
            messages.success(request, "Journal metrics recalculated from Janeway.")
            return redirect("journal_metrics_manager")
        if action != "save":
            return HttpResponseBadRequest("Unknown metrics action.")

        form = JournalMetricsForm(request.POST, instance=metrics)
        if form.is_valid():
            instance = form.save(commit=False)
            instance.journal = journal  # Journal ID is never trusted from POST.
            if instance.pk:
                instance.save(update_fields=[*form.fields.keys(), "updated_at"])
            else:
                instance.save()
            messages.success(request, "Journal metrics policies saved.")
            return redirect("journal_metrics_manager")
    else:
        form = JournalMetricsForm(instance=metrics)

    return render(
        request,
        "admin/journal/metrics.html",
        {"form": form, "metrics": metrics, "journal": journal},
    )
