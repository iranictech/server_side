"""HTTP integration tests for native Janeway reviewer matching."""

import json
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.template.loader import get_template
from django.test import Client, TestCase, override_settings
from django.urls import reverse, resolve

from core.models import Account, AccountRole, Role, XSLFile
from journal.models import Journal
from press.models import Press
from submission.models import (
    Article,
    FrozenAuthor,
    STAGE_UNDER_REVIEW,
)
from utils.install import update_settings


@override_settings(
    ROOT_URLCONF="reviewer_matching.tests.native_http_urls",
    ALLOWED_HOSTS=[
        "rma.testserver",
        "rmb.testserver",
        "press.testserver",
        "testserver",
    ],
    REVIEWER_MATCHING_ALLOW_EXTERNAL_REQUESTS=False,
    REVIEWER_MATCHING_ALLOW_ORCID_EMAIL_REQUESTS=False,
)
class NativeReviewerMatchingHTTPTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        update_settings()

        XSLFile.objects.get_or_create(
            label=settings.DEFAULT_XSL_FILE_LABEL,
            defaults={
                "file": "native-reviewer-test.xsl",
                "original_filename": "native-reviewer-test.xsl",
            },
        )

        Press.objects.create(
            name="Native Reviewer Test Press",
            domain="press.testserver",
        )

        cls.journal_a = Journal.objects.create(
            code="rma",
            domain="rma.testserver",
        )
        cls.journal_b = Journal.objects.create(
            code="rmb",
            domain="rmb.testserver",
        )

        editor_role, _ = Role.objects.get_or_create(
            slug="editor",
            defaults={"name": "Editor"},
        )

        def account(username):
            return Account.objects.create(
                username=username,
                email=username + "@example.org",
                first_name=username,
                last_name="Test",
                is_active=True,
            )

        cls.editor = account("native_http_editor")
        cls.reader = account("native_http_reader")
        cls.author_editor = account("native_http_author")

        for user in (cls.editor, cls.author_editor):
            AccountRole.objects.create(
                user=user,
                journal=cls.journal_a,
                role=editor_role,
            )

        cls.article_a = Article.objects.create(
            journal=cls.journal_a,
            title="Native reviewer matching article",
            stage=STAGE_UNDER_REVIEW,
        )
        cls.article_b = Article.objects.create(
            journal=cls.journal_b,
            title="Article from another journal",
            stage=STAGE_UNDER_REVIEW,
        )
        cls.author_article = Article.objects.create(
            journal=cls.journal_a,
            title="Article authored by an editor",
            stage=STAGE_UNDER_REVIEW,
        )

        FrozenAuthor.objects.create(
            article=cls.author_article,
            author=cls.author_editor,
            first_name="Native",
            last_name="Author",
        )

    def setUp(self):
        self.client = Client(HTTP_HOST="rma.testserver")
        self.client.force_login(self.editor)

    def url(self, name, article=None):
        article = article or self.article_a
        return reverse(
            name,
            kwargs={"article_id": article.pk},
        )

    def test_native_routes_resolve_to_native_handlers(self):
        from reviewer_matching import api, views

        targets = {
            "reviewer_matching_native_internal":
                api.internal_reviewer_matches,
            "reviewer_matching_native_combined":
                api.combined_reviewer_matches,
            "reviewer_matching_native_suggestions":
                views.suggestions_page,
        }

        for name, handler in targets.items():
            with self.subTest(name=name):
                match = resolve(self.url(name))
                self.assertIs(match.func, handler)

    def test_editor_can_open_suggestions_page(self):
        with patch(
            "reviewer_matching.views.get_internal_matches",
            return_value=[],
        ) as service:
            response = self.client.get(
                self.url("reviewer_matching_native_suggestions")
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Suggested Reviewers")
        service.assert_called_once()

    def test_editor_can_get_internal_api(self):
        with patch(
            "reviewer_matching.api.get_internal_matches",
            return_value=[],
        ) as service:
            response = self.client.get(
                self.url("reviewer_matching_native_internal")
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 0)
        self.assertEqual(response.json()["journal"], "rma")
        service.assert_called_once()

    def test_editor_can_post_combined_api(self):
        with patch(
            "reviewer_matching.api.build_combined_matches",
            return_value={"candidates": []},
        ) as service:
            response = self.client.post(
                self.url("reviewer_matching_native_combined"),
                data=json.dumps({"public_topics": []}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["journal"], "rma")
        service.assert_called_once()
        self.assertFalse(
            service.call_args.kwargs["allow_external"]
        )
        self.assertFalse(
            service.call_args.kwargs["allow_orcid_email"]
        )

    def test_other_journal_article_returns_404(self):
        for name in (
            "reviewer_matching_native_suggestions",
            "reviewer_matching_native_internal",
        ):
            with self.subTest(name=name):
                response = self.client.get(
                    self.url(name, self.article_b)
                )
                self.assertEqual(response.status_code, 404)

        response = self.client.post(
            self.url(
                "reviewer_matching_native_combined",
                self.article_b,
            ),
            data=json.dumps({"public_topics": []}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)

    def test_reader_cannot_access_endpoints(self):
        self.client.force_login(self.reader)

        for name in (
            "reviewer_matching_native_suggestions",
            "reviewer_matching_native_internal",
        ):
            with self.subTest(name=name):
                response = self.client.get(self.url(name))
                self.assertNotEqual(response.status_code, 200)

        response = self.client.post(
            self.url("reviewer_matching_native_combined"),
            data=json.dumps({"public_topics": []}),
            content_type="application/json",
        )
        self.assertNotEqual(response.status_code, 200)

    def test_anonymous_user_cannot_access_page(self):
        self.client.logout()

        response = self.client.get(
            self.url("reviewer_matching_native_suggestions")
        )

        self.assertNotEqual(response.status_code, 200)

    def test_article_author_with_editor_role_is_blocked(self):
        self.client.force_login(self.author_editor)

        response = self.client.get(
            self.url(
                "reviewer_matching_native_suggestions",
                self.author_article,
            )
        )

        self.assertNotEqual(response.status_code, 200)

    def test_combined_api_requires_csrf(self):
        secure_client = Client(
            HTTP_HOST="rma.testserver",
            enforce_csrf_checks=True,
        )
        secure_client.force_login(self.editor)

        response = secure_client.post(
            self.url("reviewer_matching_native_combined"),
            data=json.dumps({"public_topics": []}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)

    def test_api_http_methods_are_restricted(self):
        post_response = self.client.post(
            self.url("reviewer_matching_native_internal")
        )

        get_response = self.client.get(
            self.url("reviewer_matching_native_combined")
        )

        self.assertEqual(post_response.status_code, 405)
        self.assertEqual(get_response.status_code, 405)


    def test_editor_page_renders_candidate_fields(self):
        candidate = {
            "account_id": 100,
            "name": "Dr. Example Researcher",
            "source": "janeway",
            "research_interests": [
                "Fuzzy Logic",
                "Decision Making",
            ],
            "matched_keywords": ["Fuzzy Logic"],
            "active_reviews": 2,
            "expertise_evidence": "exact_keyword_overlap",
            "coi_status": "not_fully_checked",
            "invitation_ready": False,
        }

        with patch(
            "reviewer_matching.views.get_internal_matches",
            return_value=[candidate],
        ) as service:
            response = self.client.get(
                self.url("reviewer_matching_native_suggestions")
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dr. Example Researcher")
        self.assertContains(response, "Fuzzy Logic")
        self.assertContains(response, "exact_keyword_overlap")
        self.assertContains(response, "<td>2</td>", html=True)
        service.assert_called_once()

    def test_candidate_name_is_html_escaped(self):
        injected_name = "<img src=x onerror=alert(1)>"

        candidate = {
            "name": injected_name,
            "matched_keywords": [],
            "active_reviews": None,
            "expertise_evidence": "insufficient_evidence",
        }

        with patch(
            "reviewer_matching.views.get_internal_matches",
            return_value=[candidate],
        ):
            response = self.client.get(
                self.url("reviewer_matching_native_suggestions")
            )

        self.assertEqual(response.status_code, 200)

        html = response.content.decode("utf-8")

        self.assertNotIn(injected_name, html)
        self.assertIn("&lt;img", html)
        self.assertContains(response, "No exact match")
        self.assertContains(response, "Unknown")

    def test_native_template_is_used(self):
        template = get_template(
            "reviewer_matching/suggestions.html"
        )

        expected = (
            Path(settings.BASE_DIR)
            / "templates/reviewer_matching/suggestions.html"
        )

        self.assertEqual(
            Path(template.origin.name).resolve(),
            expected.resolve(),
        )


    def test_real_reviewer_orm_to_html_pipeline(self):
        """Verify real ORM selection, matching, rendering and exclusion."""
        from core.models import Account, AccountRole, Role
        from submission.models import FrozenAuthor
        from reviewer_matching.services import get_internal_matches

        keyword_text = "Fuzzy Logic"

        keyword_model = self.article_a.keywords.model
        keyword, _ = keyword_model.objects.get_or_create(
            word=keyword_text,
        )
        self.article_a.keywords.add(keyword)

        interest_model = Account._meta.get_field(
            "interest"
        ).remote_field.model

        interest, _ = interest_model.objects.get_or_create(
            name=keyword_text,
        )

        reviewer_role, _ = Role.objects.get_or_create(
            slug="reviewer",
            defaults={"name": "Reviewer"},
        )

        eligible = Account.objects.create(
            username="r621_eligible_reviewer",
            email="r621_eligible@example.org",
            first_name="Eligible",
            last_name="Researcher",
            is_active=True,
        )

        other_journal = Account.objects.create(
            username="r621_other_reviewer",
            email="r621_other@example.org",
            first_name="OtherJournal",
            last_name="Researcher",
            is_active=True,
        )

        AccountRole.objects.create(
            user=eligible,
            journal=self.journal_a,
            role=reviewer_role,
        )

        AccountRole.objects.create(
            user=other_journal,
            journal=self.journal_b,
            role=reviewer_role,
        )

        eligible.interest.add(interest)
        other_journal.interest.add(interest)

        # Real database -> reviewer selection -> ranking.
        matches = get_internal_matches(
            self.article_a,
            self.editor,
        )

        ids = [row["account_id"] for row in matches]

        self.assertIn(eligible.pk, ids)
        self.assertNotIn(other_journal.pk, ids)

        selected = next(
            row for row in matches
            if row["account_id"] == eligible.pk
        )

        self.assertIn(
            keyword_text,
            selected["matched_keywords"],
        )
        self.assertEqual(
            selected["expertise_evidence"],
            "exact_keyword_overlap",
        )
        self.assertEqual(
            selected["coi_status"],
            "not_fully_checked",
        )
        self.assertFalse(selected["invitation_ready"])

        # Real HTTP request, without mocking the matching service.
        response = self.client.get(
            self.url("reviewer_matching_native_suggestions")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            eligible.full_name(),
        )
        self.assertContains(response, keyword_text)
        self.assertNotContains(
            response,
            other_journal.full_name(),
        )

        # Once the reviewer becomes an article author,
        # that account must no longer be suggested.
        FrozenAuthor.objects.create(
            article=self.article_a,
            author=eligible,
            first_name="Eligible",
            last_name="Researcher",
        )

        excluded_matches = get_internal_matches(
            self.article_a,
            self.editor,
        )

        self.assertNotIn(
            eligible.pk,
            [row["account_id"] for row in excluded_matches],
        )

        excluded_response = self.client.get(
            self.url("reviewer_matching_native_suggestions")
        )

        self.assertEqual(excluded_response.status_code, 200)
        self.assertNotContains(
            excluded_response,
            eligible.full_name(),
        )


    def test_article_topics_require_explicit_approval(self):
        import json
        from unittest.mock import patch

        payload = {"use_article_keywords": True}

        with patch(
            "reviewer_matching.api.build_combined_matches"
        ) as builder:
            response = self.client.post(
                self.url("reviewer_matching_native_combined"),
                data=json.dumps(payload),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 400)
        builder.assert_not_called()

    def test_article_topics_come_from_database_not_request(self):
        import json
        from unittest.mock import patch

        keyword_model = self.article_a.keywords.model
        keyword, _ = keyword_model.objects.get_or_create(
            word="Fuzzy Logic",
        )
        self.article_a.keywords.add(keyword)

        payload = {
            "use_article_keywords": True,
            "public_topics_approved": True,
            "approved_article_topics": ["Fuzzy Logic"],
        }

        with patch(
            "reviewer_matching.api.build_combined_matches",
            return_value={
                "results": {"internal": [], "external": []},
                "external_status": "disabled",
            },
        ) as builder:
            response = self.client.post(
                self.url("reviewer_matching_native_combined"),
                data=json.dumps(payload),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        builder.assert_called_once()
        self.assertEqual(
            builder.call_args.kwargs["public_topics"],
            ["Fuzzy Logic"],
        )

    def test_article_topics_reject_manual_topic_override(self):
        import json
        from unittest.mock import patch

        payload = {
            "use_article_keywords": True,
            "public_topics_approved": True,
            "public_topics": ["Unrelated Topic"],
        }

        with patch(
            "reviewer_matching.api.build_combined_matches"
        ) as builder:
            response = self.client.post(
                self.url("reviewer_matching_native_combined"),
                data=json.dumps(payload),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 400)
        builder.assert_not_called()

    def test_article_topics_reject_empty_keyword_list(self):
        import json
        from unittest.mock import patch

        self.assertFalse(self.article_a.keywords.exists())

        payload = {
            "use_article_keywords": True,
            "public_topics_approved": True,
        }

        with patch(
            "reviewer_matching.api.build_combined_matches"
        ) as builder:
            response = self.client.post(
                self.url("reviewer_matching_native_combined"),
                data=json.dumps(payload),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 400)
        builder.assert_not_called()


    def test_external_ui_disabled_by_default(self):
        keyword, _ = self.article_a.keywords.model.objects.get_or_create(
            word="Fuzzy Logic",
        )
        self.article_a.keywords.add(keyword)

        response = self.client.get(
            self.url("reviewer_matching_native_suggestions")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "OpenAlex discovery is disabled by the administrator.",
        )
        self.assertContains(response, "Fuzzy Logic")
        self.assertNotContains(response, 'id="rm-openalex-form"')

    def test_external_ui_enabled_shows_article_topics(self):
        from django.test import override_settings

        keyword, _ = self.article_a.keywords.model.objects.get_or_create(
            word="Fuzzy Logic",
        )
        self.article_a.keywords.add(keyword)

        with override_settings(
            REVIEWER_MATCHING_ALLOW_EXTERNAL_REQUESTS=True
        ):
            response = self.client.get(
                self.url("reviewer_matching_native_suggestions")
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Fuzzy Logic")
        self.assertContains(response, 'id="rm-openalex-form"')
        self.assertContains(response, 'id="rm-openalex-consent"')
        self.assertContains(response, 'id="rm-openalex-results"')
        self.assertNotContains(response, 'name="public_topics"')

    def test_external_ui_no_topics_disables_search(self):
        from django.test import override_settings

        self.assertFalse(self.article_a.keywords.exists())

        with override_settings(
            REVIEWER_MATCHING_ALLOW_EXTERNAL_REQUESTS=True
        ):
            response = self.client.get(
                self.url("reviewer_matching_native_suggestions")
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "No eligible article keywords are available",
        )
        self.assertNotContains(response, 'id="rm-openalex-form"')

    def test_external_ui_get_is_network_free(self):
        from django.test import override_settings
        from unittest.mock import patch

        keyword, _ = self.article_a.keywords.model.objects.get_or_create(
            word="Fuzzy Logic",
        )
        self.article_a.keywords.add(keyword)

        with (
            override_settings(
                REVIEWER_MATCHING_ALLOW_EXTERNAL_REQUESTS=True
            ),
            patch(
                "reviewer_matching.combined.discover_external_researchers"
            ) as discovery,
            patch(
                "reviewer_matching.combined.fetch_public_email"
            ) as email_lookup,
        ):
            response = self.client.get(
                self.url("reviewer_matching_native_suggestions")
            )

        self.assertEqual(response.status_code, 200)
        discovery.assert_not_called()
        email_lookup.assert_not_called()


    def test_article_topics_require_approved_snapshot(self):
        import json
        from unittest.mock import patch

        keyword, _ = self.article_a.keywords.model.objects.get_or_create(
            word="Fuzzy Logic",
        )
        self.article_a.keywords.add(keyword)

        payload = {
            "use_article_keywords": True,
            "public_topics_approved": True,
        }

        with patch(
            "reviewer_matching.api.build_combined_matches"
        ) as builder:
            response = self.client.post(
                self.url("reviewer_matching_native_combined"),
                data=json.dumps(payload),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 409)
        builder.assert_not_called()

    def test_article_topics_changed_after_preview_are_rejected(self):
        import json
        from django.test import override_settings
        from unittest.mock import patch

        keyword_model = self.article_a.keywords.model

        first, _ = keyword_model.objects.get_or_create(
            word="Fuzzy Logic",
        )
        self.article_a.keywords.add(first)

        with override_settings(
            REVIEWER_MATCHING_ALLOW_EXTERNAL_REQUESTS=True
        ):
            preview = self.client.get(
                self.url("reviewer_matching_native_suggestions")
            )

        self.assertEqual(preview.status_code, 200)
        self.assertContains(preview, "Fuzzy Logic")

        second, _ = keyword_model.objects.get_or_create(
            word="Decision Making",
        )
        self.article_a.keywords.add(second)

        payload = {
            "use_article_keywords": True,
            "public_topics_approved": True,
            "approved_article_topics": ["Fuzzy Logic"],
        }

        with patch(
            "reviewer_matching.api.build_combined_matches"
        ) as builder:
            response = self.client.post(
                self.url("reviewer_matching_native_combined"),
                data=json.dumps(payload),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 409)
        builder.assert_not_called()

    def test_article_topics_reject_forged_snapshot(self):
        import json
        from unittest.mock import patch

        keyword, _ = self.article_a.keywords.model.objects.get_or_create(
            word="Fuzzy Logic",
        )
        self.article_a.keywords.add(keyword)

        payload = {
            "use_article_keywords": True,
            "public_topics_approved": True,
            "approved_article_topics": ["Unrelated Research"],
        }

        with patch(
            "reviewer_matching.api.build_combined_matches"
        ) as builder:
            response = self.client.post(
                self.url("reviewer_matching_native_combined"),
                data=json.dumps(payload),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 409)
        builder.assert_not_called()
