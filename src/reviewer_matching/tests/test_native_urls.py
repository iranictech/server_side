"""URL and HTTP-method tests for native Reviewer Matching."""

from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import resolve, reverse

from reviewer_matching.api import (
    combined_reviewer_matches,
    internal_reviewer_matches,
)


@override_settings(ROOT_URLCONF="review.urls")
class NativeReviewerMatchingURLTests(SimpleTestCase):

    def test_internal_route(self):
        url = reverse(
            "reviewer_matching_native_internal",
            kwargs={"article_id": 123},
        )

        self.assertEqual(
            url,
            "/manager/reviewer-matching/article/123/internal/",
        )

        match = resolve(url)

        self.assertIs(match.func, internal_reviewer_matches)
        self.assertEqual(match.kwargs["article_id"], "123")

    def test_combined_route(self):
        url = reverse(
            "reviewer_matching_native_combined",
            kwargs={"article_id": 123},
        )

        self.assertEqual(
            url,
            "/manager/reviewer-matching/article/123/combined/",
        )

        match = resolve(url)

        self.assertIs(match.func, combined_reviewer_matches)
        self.assertEqual(match.kwargs["article_id"], "123")

    def test_internal_api_rejects_post(self):
        request = RequestFactory().post(
            "/manager/reviewer-matching/article/123/internal/"
        )

        response = internal_reviewer_matches(
            request, article_id="123"
        )

        self.assertEqual(response.status_code, 405)

    def test_combined_api_rejects_get(self):
        request = RequestFactory().get(
            "/manager/reviewer-matching/article/123/combined/"
        )

        response = combined_reviewer_matches(
            request, article_id="123"
        )

        self.assertEqual(response.status_code, 405)
