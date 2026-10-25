from django.contrib import messages
from django.http import Http404
from security.decorators import editor_or_journal_manager_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import AbstractIndexingForm
from .models import AbstractIndexing

from django.contrib.contenttypes.models import ContentType
from django.views.decorators.http import require_POST



def journal_context_required(func):
    from functools import wraps

    @wraps(func)
    def wrapper(request, *args, **kwargs):
        if getattr(request, "journal", None) is None:
            raise Http404()
        return func(request, *args, **kwargs)

    return wrapper


def indexing(request):
    indexings = AbstractIndexing.objects.filter(
        journal=request.journal,
        is_active=True,
    ).order_by(
        "ordering",
        "name",
    )

    return render(
        request,
        "journal/indexing.html",
        {
            "indexings": indexings,
        },
    )



@journal_context_required
@editor_or_journal_manager_required
def abstract_indexing_config(request):
    from django.contrib.contenttypes.models import ContentType
    from core.models import HomepageElement

    journal = request.journal

    indexings = AbstractIndexing.objects.filter(
        journal=journal,
    ).order_by(
        "ordering",
        "name",
    )

    content_type = ContentType.objects.get_for_model(journal)

    homepage_registered = HomepageElement.objects.filter(
        name="Abstract Indexing",
        content_type=content_type,
        object_id=journal.pk,
    ).exists()

    return render(
        request,
        "abstract_indexing/indexing_settings.html",
        {
            "indexings": indexings,
            "homepage_registered": homepage_registered,
        },
    )



@journal_context_required
@editor_or_journal_manager_required
def abstract_indexing_add(request):
    if request.method == "POST":
        form = AbstractIndexingForm(
            request.POST,
            request.FILES,
        )

        if form.is_valid():
            indexing = form.save(commit=False)
            indexing.journal = request.journal
            indexing.save()

            messages.success(
                request,
                "Abstract indexing added successfully.",
            )

            return redirect("abstract_indexing_config")

    else:
        form = AbstractIndexingForm()

    return render(
        request,
        "abstract_indexing/indexing_form.html",
        {
            "form": form,
            "title": "Add Abstract Indexing",
        },
    )


@journal_context_required
@editor_or_journal_manager_required
def abstract_indexing_edit(request, pk):
    indexing = get_object_or_404(
        AbstractIndexing,
        pk=pk,
        journal=request.journal,
    )

    if request.method == "POST":
        form = AbstractIndexingForm(
            request.POST,
            request.FILES,
            instance=indexing,
        )

        if form.is_valid():
            form.save()

            messages.success(
                request,
                "Abstract indexing updated successfully.",
            )

            return redirect("abstract_indexing_config")

    else:
        form = AbstractIndexingForm(instance=indexing)

    return render(
        request,
        "abstract_indexing/indexing_form.html",
        {
            "form": form,
            "title": "Edit Abstract Indexing",
        },
    )


@journal_context_required
@editor_or_journal_manager_required
@require_POST
def abstract_indexing_delete(request, pk):
    indexing = get_object_or_404(
        AbstractIndexing,
        pk=pk,
        journal=request.journal,
    )

    if request.method == "POST":
        indexing.delete()

        messages.success(
            request,
            "Abstract indexing deleted successfully.",
        )

    return redirect("abstract_indexing_config")



@journal_context_required
@editor_or_journal_manager_required
@require_POST
def abstract_indexing_register_homepage(request):
    """
    Register Abstract Indexing as an available homepage element
    for the current journal only.
    """
    from core.models import HomepageElement

    journal = request.journal
    content_type = ContentType.objects.get_for_model(journal)

    element, created = HomepageElement.objects.get_or_create(
        name="Abstract Indexing",
        content_type=content_type,
        object_id=journal.pk,
        defaults={
            "configure_url": "abstract_indexing_config",
            "template_path": "journal/homepage_elements/indexing.html",
            "has_config": True,
            "available_to_press": False,
            "active": False,
        },
    )

    if created:
        messages.success(
            request,
            "Abstract Indexing added to Homepage Elements.",
        )
    else:
        messages.info(
            request,
            "Abstract Indexing is already registered for this journal.",
        )

    return redirect("abstract_indexing_config")
