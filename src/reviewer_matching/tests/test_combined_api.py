import json
import unittest

from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import RequestFactory
from django.urls import reverse
from submission.models import STAGE_UNDER_REVIEW

from reviewer_matching.api import combined_reviewer_matches


class CombinedAPITests(unittest.TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.journal = SimpleNamespace(code="ua")
        self.article = SimpleNamespace(
            pk=123,
            journal=self.journal,
            author_accounts=[],
            stage=STAGE_UNDER_REVIEW,
            editor_override=lambda user: False,
        )

    def make_user(self, editor=True):
        return SimpleNamespace(
            pk=50,
            email="editor@example.org",
            is_anonymous=False,
            is_active=True,
            is_staff=False,
            is_editor=lambda request: editor,
            has_senior_editor_role=lambda request: editor,
            is_journal_manager=lambda journal: False,
            is_section_editor=lambda request: False,
            accountrole_set=SimpleNamespace(filter=lambda **kwargs: []),
        )

    def make_request(self, payload, *, editor=True):
        request = self.factory.post(
            "/review/manager/reviewer-matches/123/combined/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        request.user = self.make_user(editor)
        request.journal = self.journal
        request._dont_enforce_csrf_checks = True
        return request

    def invoke(self, request, article=None):
        article = article or self.article

        def lookup(model, **kwargs):
            if kwargs.get("journal") is not article.journal:
                raise Http404
            return article

        result = {
            "article_id": 123,
            "results": {"internal": [], "external": []},
        }

        with (
            patch(
                "reviewer_matching.api.get_object_or_404",
                side_effect=lookup,
            ),
            patch(
                "reviewer_matching.api.build_combined_matches",
                return_value=result,
            ) as matching,
        ):
            response = combined_reviewer_matches(request, article_id=123)
            return response, matching.call_count

    def test_url_resolves(self):
        """Resolve the combined API through native Django URLs."""
        from django.test import override_settings
        from django.urls import resolve, reverse
        from reviewer_matching.api import combined_reviewer_matches

        with override_settings(ROOT_URLCONF="review.urls"):
            url = reverse(
                "reviewer_matching_native_combined",
                kwargs={"article_id": 123},
            )

            self.assertEqual(
                url,
                "/manager/reviewer-matching/article/123/combined/",
            )

            resolved = resolve(url)

            self.assertIs(
                resolved.func,
                combined_reviewer_matches,
            )
            self.assertEqual(
                resolved.kwargs["article_id"],
                "123",
            )

    def test_authorized_editor(self):
        request = self.make_request(
            {
                "public_topics": ["Fuzzy Logic"],
                "public_topics_approved": True,
            }
        )

        response, calls = self.invoke(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(calls, 1)
        self.assertEqual(
            json.loads(response.content)["journal"],
            "ua",
        )

    def test_non_editor_denied(self):
        request = self.make_request(
            {"public_topics": []},
            editor=False,
        )

        with self.assertRaises(PermissionDenied):
            self.invoke(request)

    def test_cross_journal_denied(self):
        request = self.make_request({"public_topics": []})

        foreign_article = SimpleNamespace(
            pk=123,
            journal=SimpleNamespace(code="ojavc"),
            author_accounts=[],
        )

        with self.assertRaises(Http404):
            self.invoke(request, article=foreign_article)

    def test_article_author_denied(self):
        request = self.make_request({"public_topics": []})

        article = SimpleNamespace(
            pk=123,
            journal=self.journal,
            author_accounts=[request.user],
            stage=STAGE_UNDER_REVIEW,
            editor_override=lambda user: False,
        )

        with self.assertRaises(PermissionDenied):
            self.invoke(request, article=article)

    def test_public_topics_need_approval(self):
        request = self.make_request(
            {
                "public_topics": ["Machine Learning"],
                "public_topics_approved": False,
            }
        )

        response, calls = self.invoke(request)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(calls, 0)

    def test_invalid_limit(self):
        request = self.make_request(
            {
                "public_topics": [],
                "internal_limit": 5000,
            }
        )

        response, calls = self.invoke(request)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(calls, 0)

    def test_csrf_required(self):
        request = self.make_request({"public_topics": []})
        request._dont_enforce_csrf_checks = False

        response, calls = self.invoke(request)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(calls, 0)
