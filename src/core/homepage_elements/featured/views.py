from django.urls import reverse
from django.http import HttpResponse, HttpResponseBadRequest, Http404
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render, get_object_or_404
from core.homepage_elements.featured import models
from submission import models as submission_models

from security.decorators import editor_user_required


@editor_user_required
def featured_articles(request):
    featured_arts = models.FeaturedArticle.objects.filter(journal=request.journal)
    featured_article_pks = [f.article.pk for f in featured_arts.all()]
    articles = submission_models.Article.objects.filter(
        date_published__isnull=False, journal=request.journal
    ).exclude(pk__in=featured_article_pks)

    # Note edits are restricted to the current journal's active Editor-in-Chief.
    # The existing editor/staff/manager permissions for add, delete, and order
    # remain unchanged.
    if request.method == "POST" and "save_note" in request.POST:
        if not request.user.is_editor_in_chief(request):
            raise PermissionDenied("Only the active Editor-in-Chief can edit notes.")

        try:
            featured_pk = int(request.POST.get("save_note", ""))
        except (TypeError, ValueError):
            raise Http404("Invalid featured article")

        featured = get_object_or_404(
            models.FeaturedArticle,
            pk=featured_pk,
            journal=request.journal,
            article__journal=request.journal,
        )
        note = request.POST.get(f"editor_note_{featured.pk}", "").strip()
        if len(note) > 5000:
            return HttpResponseBadRequest("Editor's note exceeds 5000 characters.")
        featured.editor_note = note
        featured.save(update_fields=["editor_note"])
        return redirect(reverse("featured_articles_setup"))

    if request.method == "POST" and "article_id" in request.POST:
        article_id = request.POST.get("article_id")
        article = get_object_or_404(
            submission_models.Article,
            pk=article_id,
            journal=request.journal,
            date_published__isnull=False,
        )

        # The optional note belongs to the article being selected, not to the
        # editor profile or the Article abstract.
        new_note = request.POST.get("new_editor_note", "").strip()
        if new_note and not request.user.is_editor_in_chief(request):
            raise PermissionDenied("Only the active Editor-in-Chief can add notes.")
        if len(new_note) > 5000:
            return HttpResponseBadRequest("Editor's note exceeds 5000 characters.")

        if models.FeaturedArticle.objects.filter(
            journal=request.journal, article=article
        ).exists():
            return HttpResponseBadRequest("Article is already featured.")

        models.FeaturedArticle.objects.create(
            article=article,
            journal=request.journal,
            added_by=request.user,
            sequence=request.journal.next_featured_article_order(),
            editor_note=new_note,
        )

        return redirect(reverse("featured_articles_setup"))

    if "delete" in request.POST:
        article_id = request.POST.get("delete")
        featured_article = get_object_or_404(
            models.FeaturedArticle, article__pk=article_id, journal=request.journal
        )
        featured_article.delete()
        return redirect(reverse("featured_articles_setup"))

    template = "featured_setup.html"
    context = {
        "featured_articles": featured_arts,
        "can_edit_editor_note": request.user.is_editor_in_chief(request),
        "articles": articles,
    }

    return render(request, template, context)


@editor_user_required
def featured_articles_order(request):
    if request.POST:
        ids = request.POST.getlist("article[]")
        ids = [int(_id) for _id in ids]

        for fa in models.FeaturedArticle.objects.filter(journal=request.journal):
            fa.sequence = ids.index(fa.pk)
            fa.save()

    return HttpResponse("Thanks")
