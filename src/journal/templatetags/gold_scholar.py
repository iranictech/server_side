"""Google Scholar citation retrieval and cache-only rendering for Gold homepage.

This module deliberately does not modify Article.citation_count or require migrations.
Citation source: Google Scholar via the unofficial scholarly library.
"""
import json
import os
import re
import tempfile
import unicodedata
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

from django import template
from journal.gold_article_identity import identity_fingerprint
from submission.models import Article, STAGE_PUBLISHED

register = template.Library()
CACHE_DIR = Path(os.environ.get('GOLD_SCHOLAR_CACHE_DIR', '/var/lib/janeway/gold-scholar'))


def _cache_path(journal):
    return CACHE_DIR / ('journal-%d.json' % journal.pk)


def _normalize(text):
    text = unicodedata.normalize('NFKC', str(text or ''))
    text = re.split(r'\bAbstract\b', text, maxsplit=1, flags=re.I)[0]
    text = re.sub(r'[^\w\s-]', ' ', text.lower(), flags=re.U)
    return ' '.join(text.split())


def _load_cache(journal):
    path = _cache_path(journal)
    try:
        raw = json.loads(path.read_text(encoding='utf-8'))
        if raw.get('journal_id') != journal.pk or raw.get('source') != 'google_scholar':
            return {}
        return raw.get('articles', {})
    except (OSError, ValueError, TypeError):
        return {}


@register.simple_tag
def gold_scholar_most_cited(journal, limit=12):
    """Display published articles with verified citations or a placeholder."""

    if journal is None:
        return []

    cache = _load_cache(journal)

    articles = Article.objects.filter(
        journal=journal,
        stage=STAGE_PUBLISHED
    ).order_by("-date_published", "-pk")

    result = []

    for article in articles:

        title = _normalize(article.title)

        # Exclude synthetic and test articles.
        if len(title) < 24 or title.startswith(
            ("demo ", "test ", "synthetic ")
        ):
            continue

        article.gold_citation_count = None
        article.gold_citation_display = "-"

        entry = cache.get(str(article.pk), {})

        count = entry.get("citations")

        if (
            entry.get("status") == "verified"
            and type(count) is int
            and count >= 0
            and entry.get("normalized_title") == title
        ):
            authors = [
                {
                    "first_name": author.first_name or "",
                    "middle_name": author.middle_name or "",
                    "last_name": author.last_name or "",
                    "full_name": author.full_name(),
                    "is_corporate": author.is_corporate
                }
                for author in article.frozen_authors().order_by(
                    "order", "pk"
                )
            ]

            doi = article.get_doi()

            identity = {
                "title": str(article.title or ""),
                "year": (
                    article.date_published.year
                    if article.date_published else None
                ),
                "doi": str(doi) if doi else None,
                "authors": authors
            }

            if (
                entry.get("identity_fingerprint")
                == identity_fingerprint(identity)
            ):
                article.gold_citation_count = count

                if count > 0:
                    article.gold_citation_display = str(count)

        result.append(article)

    result.sort(
        key=lambda a: a.gold_citation_count or 0,
        reverse=True
    )

    return result[:max(1, min(int(limit), 12))]



def _fetch_match(title, year, scholarly, max_results=5):
    wanted = _normalize(title)
    if len(wanted) < 24 or wanted.startswith(('demo ', 'test ', 'synthetic ')):
        return {'status': 'skipped', 'reason': 'non-scholarly or test title'}
    candidates = []
    # External search may raise timeouts/CAPTCHA. Never convert errors to citation zero.
    for index, item in enumerate(scholarly.search_pubs(wanted)):
        if index >= max_results:
            break
        bib = item.get('bib') or {}
        candidate_title = bib.get('title') or ''
        similarity = SequenceMatcher(None, wanted, _normalize(candidate_title)).ratio()
        found_year = bib.get('pub_year') or bib.get('year')
        if year and found_year and str(found_year) != str(year):
            continue
        count = item.get('num_citations')
        if similarity >= 0.96 and isinstance(count, int) and count >= 0:
            candidates.append((similarity, item, candidate_title))
    if len(candidates) != 1:
        return {'status': 'unverified', 'reason': 'no unambiguous exact-title match'}
    score, match, scholar_title = candidates[0]
    return {'status': 'verified', 'citations': match['num_citations'],
            'scholar_title': scholar_title, 'match_score': round(score, 4),
            'scholar_pub_id': match.get('author_pub_id'),
            'scholar_url': match.get('pub_url')}


def update_journal_cache(journal, apply=False, per_run=10):
    """Fetch a bounded number of published papers; write atomically only if apply=True."""
    from scholarly import scholarly
    now = datetime.now(timezone.utc).isoformat()
    existing = _load_cache(journal)
    updated = dict(existing)
    articles = list(Article.objects.filter(journal=journal, stage=STAGE_PUBLISHED)
                    .order_by('-date_published', '-pk')[:per_run])
    report = []
    for article in articles:
        title = _normalize(article.title)
        year = article.date_published.year if article.date_published else None
        try:
            value = _fetch_match(article.title, year, scholarly)
        except Exception as exc:
            value = {'status': 'error', 'reason': type(exc).__name__}
        if value['status'] == 'verified':
            value['normalized_title'] = title
            value['checked_at'] = now
            updated[str(article.pk)] = value
        elif str(article.pk) not in updated or updated[str(article.pk)].get('normalized_title') != title:
            # Preserve previously validated citation counts on transient failures.
            value['normalized_title'] = title
            value['checked_at'] = now
            updated[str(article.pk)] = value
        report.append((article.pk, value['status'], value.get('citations'), value.get('reason')))
    if apply:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        document = {'journal_id': journal.pk, 'journal_code': journal.code,
                    'source': 'google_scholar', 'updated_at': now, 'articles': updated}
        fd, tmp = tempfile.mkstemp(prefix='.gold-scholar-', dir=str(CACHE_DIR))
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as out:
                json.dump(document, out, ensure_ascii=False, indent=2)
                out.flush()
                os.fsync(out.fileno())
            os.chmod(tmp, 0o644)
            os.replace(tmp, _cache_path(journal))
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    return report
