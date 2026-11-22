"""Gold homepage presentation context. Read-only and isolated by journal.

Requires no schema migration. Uses native Janeway HomepageElement, Popular
Articles, FeaturedArticle, Issue, EditorialGroup and AbstractIndexing records.
"""

import re

from django import template

register = template.Library()


def _published_articles(journal):
    from submission.models import Article, STAGE_PUBLISHED
    return Article.objects.filter(
        journal=journal, stage=STAGE_PUBLISHED
    ).order_by("-date_published", "-pk")


@register.simple_tag
def gold_element_context(journal, element_name):
    if journal is None:
        return {}

    if element_name == "Abstract Indexing":
        from plugins.abstract_indexing.models import AbstractIndexing
        return {
            "indexings": list(
                AbstractIndexing.objects.filter(
                    journal=journal, is_active=True
                ).order_by("ordering", "name")
            ),
        }

    if element_name == "Popular Articles":
        # GOLD_REAL_VIEW_COUNTS_V1
        # Total views = recorded view events + historical views.
        # Isolated to the Gold homepage; no database writes.
        from django.db.models import Count, F, IntegerField, OuterRef, Q, Subquery, Value
        from django.db.models.functions import Coalesce
        from metrics.models import HistoricArticleAccess
        from core.homepage_elements.popular import logic

        enabled, number, period = logic.get_popular_article_settings(journal)

        try:
            limit = max(1, min(int(number or 4), 12))
        except (ValueError, TypeError):
            limit = 4

        historic_views = HistoricArticleAccess.objects.filter(
            article_id=OuterRef("pk")
        ).order_by().values("views")[:1]

        articles = list(
            _published_articles(journal)
            .annotate(
                gold_current_views=Count(
                    "articleaccess",
                    filter=Q(articleaccess__type="view"),
                ),
                gold_historic_views=Coalesce(
                    Subquery(historic_views, output_field=IntegerField()),
                    Value(0),
                ),
            )
            .annotate(
                gold_view_count=F("gold_current_views") + F("gold_historic_views")
            )
            .order_by("-gold_view_count", "-date_published", "-pk")[:limit]
        )

        has_views = any(article.gold_view_count > 0 for article in articles)

        return {
            "popular_articles": articles,
            "popular_fallback_latest": not has_views,
        }

    if element_name == "Featured Articles":
        from core.homepage_elements.featured.models import FeaturedArticle
        from submission.models import STAGE_PUBLISHED

        return {
            "featured_articles": list(
                FeaturedArticle.objects.filter(
                    journal=journal,
                    article__journal=journal,
                    article__stage=STAGE_PUBLISHED,
                ).select_related("article").order_by("sequence", "pk")
            ),
        }

    return {}


@register.simple_tag
def gold_current_issue_info(journal):
    """Existing journal.current_issue and issue.articles data."""
    if not journal:
        return None
    issue = journal.current_issue
    if issue is None or issue.journal_id != journal.pk:
        return None

    from submission.models import STAGE_PUBLISHED

    published = issue.articles.filter(
        journal=journal, stage=STAGE_PUBLISHED
    ).order_by("-date_published", "-pk")
    return {
        "issue": issue,
        "article_count": published.count(),
        "lead_article": published.first(),
    }


@register.simple_tag
def gold_editor_in_chief(journal):
    """Use Janeway's editable EditorialGroup / EditorialGroupMember records.

    No name, academic rank, portrait, biography, or note is fabricated.
    """
    if not journal:
        return None

    from core.models import EditorialGroup, EditorialGroupMember

    group = (
        EditorialGroup.objects.filter(journal=journal, name__icontains="chief")
        .order_by("sequence", "pk")
        .first()
    )
    if not group:
        return None

    member = (
        EditorialGroupMember.objects.filter(group=group)
        .select_related("user").order_by("sequence", "pk").first()
    )
    if not member:
        return None

    user = member.user
    image_url = user.profile_image.url if user.profile_image else ""
    orcid = (user.orcid or "").strip().removeprefix("https://orcid.org/")
    orcid_url = (
        "https://orcid.org/" + orcid
        if re.fullmatch(r"\d{4}-\d{4}-\d{4}-[\dX]{4}", orcid)
        else ""
    )

    return {
        "name": user.full_name(),
        "image_url": image_url,
        "affiliation": user.institution or "",
        "orcid_url": orcid_url,
    }
