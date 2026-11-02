"""Tests for the native reviewer suggestion page."""

from pathlib import Path

from django.http import Http404
from django.template.loader import get_template
from django.test import (
    RequestFactory,
    SimpleTestCase,
    override_settings,
)
from django.urls import resolve, reverse

from reviewer_matching.views import suggestions_page


@override_settings(ROOT_URLCONF="review.urls")
class NativeSuggestionsTests(SimpleTestCase):
    def test_native_page_url(self):
        url = reverse(
            "reviewer_matching_native_suggestions",
            kwargs={"article_id": 123},
        )

        self.assertEqual(
            url,
            "/manager/reviewer-matching/article/123/suggestions/",
        )

        match = resolve(url)
        self.assertIs(match.func, suggestions_page)

    def test_missing_journal_rejected(self):
        request = RequestFactory().get(
            "/manager/reviewer-matching/article/123/suggestions/"
        )

        with self.assertRaises(Http404):
            suggestions_page(request, article_id="123")

    def test_native_template_discoverable(self):
        result = get_template("reviewer_matching/suggestions.html")
        self.assertIsNotNone(result)

    def test_editorial_button_present(self):
        path = (
            Path(__file__).resolve().parents[2]
            / "templates/admin/review/in_review.html"
        )
        source = path.read_text(encoding="utf-8")

        self.assertIn(
            "reviewer_matching_native_suggestions",
            source,
        )
        self.assertIn("Find Reviewers", source)

    def test_duplicate_identity_warning_is_in_editorial_template(self):
        path = (
            Path(__file__).resolve().parents[2]
            / "templates/reviewer_matching/suggestions.html"
        )
        source = path.read_text(encoding="utf-8")

        self.assertIn("candidate.possible_duplicate", source)
        self.assertIn("Possible duplicate OpenAlex records", source)

    def test_sampled_year_has_explicit_scope_warning(self):
        path = (
            Path(__file__).resolve().parents[2]
            / "templates/reviewer_matching/suggestions.html"
        )
        source = path.read_text(encoding="utf-8")

        self.assertIn("Latest Year in Sample", source)
        self.assertIn("candidate.latest_sampled_publication_year", source)
        self.assertIn("not a complete publication history", source)

    def test_manual_coi_review_and_work_evidence_visible(self):
        path = (
            Path(__file__).resolve().parents[2]
            / "templates/reviewer_matching/suggestions.html"
        )
        source = path.read_text(encoding="utf-8")

        self.assertIn("COI Evidence", source)
        self.assertIn("candidate.coauthorship_evidence_work_ids", source)
        self.assertIn("potential_coauthorship_conflict", source)
        self.assertIn("missing evidence does not", source)

    def test_internal_coi_form_is_csrf_protected_and_explicit(self):
        path = (
            Path(__file__).resolve().parents[2]
            / "templates/reviewer_matching/suggestions.html"
        )
        source = path.read_text(encoding="utf-8")

        self.assertIn("reviewer_matching_native_coi_assessment", source)
        self.assertIn("{% csrf_token %}", source)
        self.assertIn('name="rationale"', source)
        self.assertIn("Last editorial COI decision", source)
        self.assertIn("does not automatically invite the reviewer", source)
