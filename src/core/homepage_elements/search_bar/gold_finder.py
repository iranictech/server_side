"""Gold-only, read-only, CSRF-protected Journal Finder endpoint."""

import os
from html import unescape
from django.http import JsonResponse
from django.utils.html import strip_tags
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect

from .gold_finder_logic import evaluate


def _error(message, status):
    return JsonResponse({"error": message}, status=status)


@csrf_protect
@require_POST
def find_journal_fit(request):
    journal = getattr(request, "journal", None)
    if journal is None:
        return _error("A journal must be selected.", 404)

    # This endpoint is present in the shared URL configuration but is only
    # functional for Gold journals; Clean/OLH/Material are unaffected.
    if journal.get_setting("general", "journal_theme") != "gold":
        return _error("Journal Finder is not enabled for this theme.", 404)

    length = request.META.get("CONTENT_LENGTH")
    if length and length.isdigit() and int(length) > 16000:
        return _error("Input is too long.", 413)

    manuscript_text = request.POST.get("manuscript_text", "").strip()
    if not 3 <= len(manuscript_text) <= 8000:
        return _error("Enter between 3 and 8000 characters.", 400)

    topics = list(journal.keywords.order_by("word").values_list("word", flat=True)[:100])
    description = journal.get_setting("general", "journal_description") or ""
    scope = unescape(strip_tags(str(description or getattr(journal, "description", ""))))[:4000]

    # Local semantic model is OPTIONAL, never downloaded at runtime.
    local_model = os.environ.get("GOLD_FINDER_LOCAL_MODEL_DIR") or None
    result = evaluate(manuscript_text, topics, scope, local_model)
    response = JsonResponse(result, json_dumps_params={"ensure_ascii": False})
    response["Cache-Control"] = "no-store, private"
    return response
