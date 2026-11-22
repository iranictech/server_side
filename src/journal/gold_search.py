"""Gold theme journal results, initially opt-in for journal `ua`.

No schema changes. Uses Janeway metadata search and restricts PDF content matches
explicitly to published articles' public galleys.
"""
from django.contrib.postgres.search import SearchQuery, SearchVector
from django.core.paginator import Paginator
from django.db.models import Count, Prefetch, Q, Case, When, IntegerField
from django.http import HttpResponseBadRequest
from django.shortcuts import render
from django.utils import timezone

from journal.forms import SearchForm
from submission.models import Article, Section, Keyword, STAGE_PUBLISHED
from core.models import Galley

SORTS = {'relevance', 'title', '-title', '-date_published', 'date_published'}
PAGE_SIZE = 10


def gold_search(request):
    journal = request.journal
    query = request.GET.get('article_search', '').strip()
    keyword = request.GET.get('keyword', '').strip()
    sort = request.GET.get('sort', 'relevance')
    if sort not in SORTS:
        sort = 'relevance'

    # Keep aligned with Janeway SearchForm; reject rather than silently truncate.
    error = None
    if len(query) > 100:
        error = 'Please enter 100 characters or fewer.'
    elif query and len(query) < 3:
        error = 'Please enter at least 3 characters.'
    if len(keyword) > 200:
        error = 'Invalid keyword.'

    section_ids = [int(x) for x in request.GET.getlist('section') if x.isdecimal()][:30]
    keyword_ids = [int(x) for x in request.GET.getlist('subject') if x.isdecimal()][:30]
    base = Article.objects.filter(
        journal=journal, stage=STAGE_PUBLISHED, date_published__lte=timezone.now(),
    )
    matched_ids = []
    # The existing ArticleSearchManager handles authors, keywords, title, abstract,
    # and ranking. Private fulltext matches MUST NOT participate in search.
    if not error and query:
        metadata_filters = {
            'title': True, 'abstract': True, 'authors': True,
            'keywords': True, 'full_text': False, 'orcid': False,
        }
        # Janeway returns a RawQuerySet for PostgreSQL: normalize to an ID list.
        metadata = Article.objects.search(query, metadata_filters, sort=None, site=journal)
        metadata_ids = [article.pk for article in metadata]
        # Full text is restricted to PUBLIC PDF/HTML/XML galleys of this journal.
        # Do not search any submission, manuscript, peer review or private galley.
        fulltext_ids = list(base.filter(
            galley__public=True,
            galley__file__text__contents__isnull=False,
        ).annotate(
            _gold_fts=SearchVector('galley__file__text__contents'),
        ).filter(
            _gold_fts=SearchQuery(query, search_type='plain'),
        ).values_list('id', flat=True).distinct())
        matched_ids = list(dict.fromkeys(metadata_ids + fulltext_ids))
        results = base.filter(pk__in=matched_ids)
    elif not error and keyword:
        results = base.filter(keywords__word=keyword)
    else:
        results = base.none()

    # Facet options and counts are derived from the *matched*, published articles.
    # Only Sections marked filterable may appear in the filter UI.
    candidate = results.distinct()
    sections = list(Section.objects.filter(
        journal=journal, is_filterable=True, pk__in=candidate.exclude(
            section__isnull=True).values('section_id')
    ).annotate(result_count=Count('article', filter=Q(article__in=candidate), distinct=True))
      .order_by('sequence', 'name'))
    topics = list(Keyword.objects.filter(
        article__in=candidate,
    ).annotate(result_count=Count('article', filter=Q(article__in=candidate), distinct=True))
      .distinct().order_by('-result_count', 'word')[:60])

    if section_ids:
        allowed = {s.pk for s in sections}
        results = results.filter(section_id__in=set(section_ids) & allowed)
    if keyword_ids:
        allowed = {k.pk for k in topics}
        results = results.filter(keywords__pk__in=set(keyword_ids) & allowed)

    results = results.distinct()
    if sort == 'relevance' and query and matched_ids:
        # Preserve PostgreSQL manager rank order for metadata results; public-PDF-
        # only matches follow, while remaining inside the pagination queryset.
        positions = [When(pk=pk, then=pos) for pos, pk in enumerate(matched_ids)]
        results = results.annotate(
            _gold_rank_order=Case(*positions, default=len(matched_ids), output_field=IntegerField())
        ).order_by('_gold_rank_order', 'id')
    elif sort in {'title', '-title', '-date_published', 'date_published'}:
        results = results.order_by(sort, 'pk')
    else:
        results = results.order_by('-date_published', 'pk')

    paginator = Paginator(results.prefetch_related(
        'frozenauthor_set',
        Prefetch('galley_set', queryset=Galley.objects.filter(
            public=True, type='pdf', file__isnull=False
        ).select_related('file'), to_attr='gold_public_pdfs'),
    ), PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    def page_url(number):
        params = request.GET.copy()
        params['page'] = number
        return f'{request.path}?{params.urlencode()}'

    def clear_url():
        params = request.GET.copy()
        for key in ('section', 'subject', 'page'):
            params.pop(key, None)
        return f'{request.path}?{params.urlencode()}'

    page_links = [
        {'number': n, 'url': page_url(n) if isinstance(n, int) else None,
         'active': n == page_obj.number} for n in paginator.get_elided_page_range(
            number=page_obj.number, on_each_side=2, on_ends=1)
    ]
    context = {
        'articles': page_obj.object_list,
        'page_obj': page_obj,
        'paginator': paginator,
        'page_links': page_links,
        'previous_url': page_url(page_obj.previous_page_number()) if page_obj.has_previous() else '',
        'next_url': page_url(page_obj.next_page_number()) if page_obj.has_next() else '',
        'first_result': page_obj.start_index() if paginator.count else 0,
        'last_result': page_obj.end_index() if paginator.count else 0,
        'article_search': query,
        'keyword': keyword,
        'sort': sort,
        'error': error,
        'sections': sections,
        'topics': topics,
        'selected_sections': set(section_ids),
        'selected_topics': set(keyword_ids),
        'clear_filters_url': clear_url(),
        'form': SearchForm(request.GET or None),
    }
    return render(request, 'journal/search.html', context)
