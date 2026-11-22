"""Gold Journal Finder: read-only topic/scope matching (no model or migration).

This is a screening aid, not an editorial decision or admission probability.
No user text is logged, stored, or sent to remote services by this module.
"""

import os
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

STOPWORDS = frozenset(
    "a an and are as at based be by can for from has in into is it of on or our "
    "the their this to under using via we with work research results journal journals "
    "article articles study studies approach approaches method methods new novel "
    "analysis analyses data applications applied application that which these those "
    "your its about such provide proposes paper papers general important including".split()
)
TOKEN_RE = re.compile(r"[^\W_]+", flags=re.UNICODE)


def tokens(value):
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    normalized = normalized.replace("ي", "ی").replace("ك", "ک")
    return [w for w in TOKEN_RE.findall(normalized) if len(w) >= 3 and w not in STOPWORDS]


def _contains_phrase(haystack, needle):
    """Exact ordered token phrase, with punctuation and filler words normalized."""
    if not needle or len(needle) > len(haystack):
        return False
    return any(haystack[i:i + len(needle)] == needle
               for i in range(len(haystack) - len(needle) + 1))


def _topic_evidence(manuscript_tokens, topics):
    """Separate an exact phrase from all-terms or partial word overlap.

    Repeated shared vocabulary never becomes additional independent evidence.
    """
    query = set(manuscript_tokens)
    matches = []
    seen = set()
    for name in topics:
        name = str(name or '').strip()
        key = unicodedata.normalize('NFKC', name).casefold()
        if not name or key in seen:
            continue
        seen.add(key)
        phrase = tokens(name)
        topic_terms = set(phrase)
        if not topic_terms:
            continue
        overlap = topic_terms & query
        if not overlap:
            continue
        coverage = len(overlap) / len(topic_terms)
        exact_phrase = len(topic_terms) >= 2 and _contains_phrase(manuscript_tokens, phrase)
        if exact_phrase:
            evidence, weight = 'exact_phrase', 1.0
        elif coverage == 1:
            evidence, weight = 'all_terms', 0.65 if len(topic_terms) >= 2 else 0.30
        else:
            evidence, weight = 'partial_terms', 0.25 * coverage
        matches.append({
            'topic': name,
            'evidence': evidence,
            'coverage': round(coverage, 3),
            'weight': round(weight, 3),
            '_terms': topic_terms,
        })
    matches.sort(key=lambda m: (-m['weight'], -len(m['_terms']), m['topic'].casefold()))
    return matches


def _independent_exact_matches(matches):
    """Count distinct topic-phrase evidence, not variations of shared words."""
    seen_terms = set()
    independent = 0
    for match in matches:
        if match['evidence'] != 'exact_phrase':
            continue
        new_terms = match['_terms'] - seen_terms
        if not seen_terms or len(new_terms) >= 2:
            independent += 1
        seen_terms.update(match['_terms'])
    return independent


def lexical_evaluation(manuscript_text, journal_topics, journal_scope):
    manuscript_tokens = tokens(manuscript_text)
    topics = [str(topic) for topic in journal_topics]
    scope_tokens = set(tokens(journal_scope))

    if not any(tokens(topic) for topic in topics) and not scope_tokens:
        return {
            'level': 'insufficient_data',
            'label': 'Not enough journal scope information',
            'explanation': 'The journal has no configured disciplines or usable scope description.',
            'matched_topics': [],
            'scope_terms': [],
            'scope_support_terms': [],
            'analysis_mode': 'keyword_scope',
        }

    matches = _topic_evidence(manuscript_tokens, topics)
    query_set = set(manuscript_tokens)
    scope_overlaps = sorted(query_set & scope_tokens)

    # Count scope support only when it adds vocabulary NOT already present
    # in any configured topic. This avoids double-counting 'uncertainty'.
    all_topic_terms = set().union(*(set(tokens(t)) for t in topics)) if topics else set()
    scope_independent = sorted((query_set & scope_tokens) - all_topic_terms)
    exact_count = sum(m['evidence'] == 'exact_phrase' for m in matches)
    full_count = sum(m['evidence'] == 'all_terms' for m in matches)
    independent = _independent_exact_matches(matches)

    if independent >= 2 or (independent >= 1 and len(scope_independent) >= 2
                            and len(set(manuscript_tokens)) >= 6):
        level, label = 'strong_indication', 'Strong topical indication'
    elif exact_count or full_count or (
        sum(len(m['_terms'] & query_set) >= 2 for m in matches) >= 2
        and len(scope_independent) >= 2
    ):
        level, label = 'partial_indication', 'Partial topical indication'
    elif matches or len(scope_overlaps) >= 2:
        level, label = 'limited_indication', 'Limited topical indication'
    else:
        level, label = 'little_evidence', 'Little topical evidence'

    return {
        'level': level,
        'label': label,
        'explanation': (
            'This preliminary rule-based check distinguishes full topic phrases '
            'from shared words and considers independent scope terms. '
            'It is not a prediction of editorial acceptance.'
        ),
        'matched_topics': [
            {'topic': m['topic'], 'evidence': m['evidence']}
            for m in matches[:8]
        ],
        'scope_terms': scope_overlaps[:10],
        'scope_support_terms': scope_independent[:8],
        'analysis_mode': 'keyword_scope',
    }


@lru_cache(maxsize=1)
def _load_local_sentence_model(model_path):
    """Use only an already installed local model. Never download from the hub."""
    location = Path(model_path)
    if not location.is_absolute() or not location.is_dir():
        raise ValueError("Model must be a preinstalled absolute local directory")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    from sentence_transformers import SentenceTransformer  # optional dependency
    return SentenceTransformer(str(location), device="cpu", local_files_only=True)


def semantic_evaluation(manuscript_text, journal_topics, journal_scope, model_path=None):
    """Optional local semantic similarity; no network, no data persistence.

    Returns None if not configured, unavailable, or insufficient reference text.
    Cosine scores are NOT probabilities of fit and are not shown as such.
    """
    if not model_path:
        return None
    reference_items = [("topic", t) for t in journal_topics if str(t).strip()]
    if str(journal_scope).strip():
        reference_items.append(("scope", str(journal_scope)[:4000]))
    if not reference_items:
        return None

    try:
        model = _load_local_sentence_model(model_path)
        sequences = [str(manuscript_text)[:8000]] + [text for _, text in reference_items]
        embeddings = model.encode(sequences, normalize_embeddings=True, show_progress_bar=False)
        query_embedding = embeddings[0]
        similarities = [(float(query_embedding @ vector), label, text)
                        for vector, (label, text) in zip(embeddings[1:], reference_items)]
    except (ImportError, ValueError, OSError, RuntimeError, TypeError):
        return None

    similarities.sort(key=lambda result: result[0], reverse=True)
    top = similarities[0]
    return {
        "analysis_mode": "local_semantic",
        "top_reference_type": top[1],
        "top_topic": top[2] if top[1] == "topic" else None,
        "similarity_band": (
            "higher" if top[0] >= 0.55 else
            "moderate" if top[0] >= 0.35 else "lower"
        ),
        "note": "Embedding similarity is supplementary, uncalibrated evidence; not an acceptance probability.",
    }


def evaluate(manuscript_text, journal_topics, journal_scope, model_path=None):
    result = lexical_evaluation(manuscript_text, journal_topics, journal_scope)
    result["semantic"] = semantic_evaluation(manuscript_text, journal_topics, journal_scope, model_path)
    result["semantic_enabled"] = result["semantic"] is not None
    if result["semantic"] is not None and result["semantic"]["similarity_band"] == "higher":
        if result["level"] in {"limited_indication", "little_evidence"}:
            result["level"] = "possible_semantic_alignment"
            result["label"] = "Possible semantic alignment"
            result["explanation"] = (
                "A local embedding model suggests thematic similarity even though exact "
                "topic words are scarce. This is uncalibrated and requires editorial review."
            )
    return result
