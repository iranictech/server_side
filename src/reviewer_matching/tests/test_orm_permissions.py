import json

from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import RequestFactory, TestCase

from core.models import Account, AccountRole, Role, XSLFile
from journal.models import Journal
from submission.models import (
    Article,
    FrozenAuthor,
    STAGE_UNDER_REVIEW,
    STAGE_ACCEPTED,
    STAGE_UNASSIGNED,
)
from review.models import EditorAssignment, EditorOverride

from reviewer_matching.api import (
    combined_reviewer_matches,
    internal_reviewer_matches,
)
from utils.install import update_settings
from reviewer_matching.combined import build_combined_matches
from reviewer_matching.identity import resolve_janeway_orcid


class ReviewerMatchingORMPermissionTests(TestCase):
    """Real ORM and role checks against Django's temporary test DB."""

    @classmethod
    def setUpTestData(cls):
        # Initialize Janeway's default settings in the test DB.
        update_settings()

        # Required by Journal.default_xsl().
        # Database-only fixture; no real XSL file is written.
        XSLFile.objects.get_or_create(
            label=settings.DEFAULT_XSL_FILE_LABEL,
            defaults={
                "file": "reviewer-matching-test-default.xsl",
                "original_filename": "reviewer-matching-test-default.xsl",
            },
        )

        cls.journal_a = Journal.objects.create(code="rma")
        cls.journal_b = Journal.objects.create(code="rmb")

        cls.editor_role, _ = Role.objects.get_or_create(
            slug="editor",
            defaults={"name": "Editor"},
        )

        def create_account(username):
            return Account.objects.create(
                username=username,
                email=f"{username}@example.org",
                first_name=username.capitalize(),
                last_name="Test",
                password="!unusable-test-password",
                is_active=True,
            )

        cls.editor_a = create_account("rm_editor_a")
        cls.editor_b = create_account("rm_editor_b")
        cls.author_editor = create_account("rm_author_editor")
        cls.reader = create_account("rm_reader")

        for user, journal in (
            (cls.editor_a, cls.journal_a),
            (cls.editor_b, cls.journal_b),
            (cls.author_editor, cls.journal_a),
        ):
            AccountRole.objects.create(
                user=user,
                journal=journal,
                role=cls.editor_role,
            )

        cls.article_a = Article.objects.create(
            journal=cls.journal_a,
            title="Reviewer matching test article A",
            stage=STAGE_UNDER_REVIEW,
        )

        cls.article_b = Article.objects.create(
            journal=cls.journal_b,
            title="Reviewer matching test article B",
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
            first_name="Author",
            last_name="Editor",
        )

    def setUp(self):
        self.factory = RequestFactory()

    def make_request(self, user, journal, article_id, payload=None):
        if payload is None:
            payload = {"public_topics": []}

        path = f"/review/manager/reviewer-matches/{article_id}/combined/"

        request = self.factory.post(
            path,
            data=json.dumps(payload),
            content_type="application/json",
        )

        request.user = user
        request.journal = journal
        request.session = {}
        request._dont_enforce_csrf_checks = True

        return request

    def invoke(self, request, article_id):
        with (
            patch(
                "reviewer_matching.combined.get_internal_matches",
                return_value=[],
            ),
            patch(
                "reviewer_matching.combined.discover_external_researchers"
            ) as external,
        ):
            try:
                response = combined_reviewer_matches(
                    request,
                    article_id=article_id,
                )
                return response
            finally:
                external.assert_not_called()

    def test_actual_editor_role_is_recognized(self):
        request = self.make_request(
            self.editor_a,
            self.journal_a,
            self.article_a.pk,
        )

        self.assertTrue(self.editor_a.has_senior_editor_role(request))

    def test_authorized_editor_can_access_own_journal(self):
        request = self.make_request(
            self.editor_a,
            self.journal_a,
            self.article_a.pk,
        )

        response = self.invoke(request, self.article_a.pk)

        self.assertEqual(response.status_code, 200)

        payload = json.loads(response.content)

        self.assertEqual(payload["journal"], "rma")
        self.assertEqual(
            payload["external_status"],
            "not_requested",
        )
        self.assertEqual(
            payload["counts"],
            {"internal": 0, "external": 0},
        )

    def test_editor_of_other_journal_is_denied(self):
        request = self.make_request(
            self.editor_b,
            self.journal_a,
            self.article_a.pk,
        )

        with self.assertRaises(PermissionDenied):
            self.invoke(request, self.article_a.pk)

    def test_cross_journal_article_is_not_accessible(self):
        request = self.make_request(
            self.editor_a,
            self.journal_a,
            self.article_b.pk,
        )

        with self.assertRaises(Http404):
            self.invoke(request, self.article_b.pk)

    def test_author_with_editor_role_is_denied(self):
        request = self.make_request(
            self.author_editor,
            self.journal_a,
            self.author_article.pk,
        )

        self.assertTrue(
            self.author_article.author_accounts.filter(
                pk=self.author_editor.pk
            ).exists()
        )

        with self.assertRaises(PermissionDenied):
            self.invoke(request, self.author_article.pk)

    def test_reader_without_editor_role_is_denied(self):
        request = self.make_request(
            self.reader,
            self.journal_a,
            self.article_a.pk,
        )

        with self.assertRaises(PermissionDenied):
            self.invoke(request, self.article_a.pk)

    def test_external_service_disabled_even_with_approved_topics(self):
        request = self.make_request(
            self.editor_a,
            self.journal_a,
            self.article_a.pk,
            {
                "public_topics": ["Fuzzy Logic"],
                "public_topics_approved": True,
            },
        )

        response = self.invoke(request, self.article_a.pk)
        payload = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            payload["external_status"],
            "disabled",
        )

    def make_internal_request(self, user, journal, article_id, active_role=None):
        request = self.factory.get(f"/review/manager/reviewer-matches/{article_id}/")
        request.user = user
        request.journal = journal
        request.active_role_slug = active_role
        request.session = {}
        return request

    def test_eic_active_role_can_access_combined(self):
        role, _ = Role.objects.get_or_create(
            slug="editor-in-chief",
            defaults={"name": "Editor-in-Chief"},
        )
        AccountRole.objects.get_or_create(
            user=self.editor_a,
            journal=self.journal_a,
            role=role,
        )
        request = self.make_request(self.editor_a, self.journal_a, self.article_a.pk)
        request.active_role_slug = "editor-in-chief"
        self.assertTrue(self.editor_a.has_senior_editor_role(request))
        self.assertEqual(
            self.invoke(request, self.article_a.pk).status_code,
            200,
        )

    def test_active_reviewer_cannot_use_combined(self):
        role, _ = Role.objects.get_or_create(
            slug="reviewer",
            defaults={"name": "Reviewer"},
        )
        AccountRole.objects.get_or_create(
            user=self.editor_a,
            journal=self.journal_a,
            role=role,
        )
        request = self.make_request(self.editor_a, self.journal_a, self.article_a.pk)
        request.active_role_slug = "reviewer"
        with self.assertRaises(PermissionDenied):
            self.invoke(request, self.article_a.pk)

    def test_section_editor_assigned_can_access(self):
        role, _ = Role.objects.get_or_create(
            slug="section-editor",
            defaults={"name": "Section Editor"},
        )
        AccountRole.objects.get_or_create(
            user=self.editor_b,
            journal=self.journal_a,
            role=role,
        )
        EditorAssignment.objects.create(
            article=self.article_a,
            editor=self.editor_b,
            editor_type="section-editor",
        )
        request = self.make_request(self.editor_b, self.journal_a, self.article_a.pk)
        request.active_role_slug = "section-editor"
        self.assertEqual(
            self.invoke(request, self.article_a.pk).status_code,
            200,
        )

    def test_unassigned_section_editor_is_denied(self):
        role, _ = Role.objects.get_or_create(
            slug="section-editor",
            defaults={"name": "Section Editor"},
        )
        AccountRole.objects.get_or_create(
            user=self.editor_b,
            journal=self.journal_a,
            role=role,
        )
        request = self.make_request(self.editor_b, self.journal_a, self.article_a.pk)
        request.active_role_slug = "section-editor"
        with self.assertRaises(PermissionDenied):
            self.invoke(request, self.article_a.pk)

    def test_author_override_allows_combined(self):
        EditorOverride.objects.create(
            article=self.author_article,
            editor=self.author_editor,
        )
        request = self.make_request(
            self.author_editor,
            self.journal_a,
            self.author_article.pk,
        )
        request.active_role_slug = "editor"
        self.assertEqual(
            self.invoke(request, self.author_article.pk).status_code,
            200,
        )

    def test_internal_author_without_override_denied(self):
        request = self.make_internal_request(
            self.author_editor,
            self.journal_a,
            self.author_article.pk,
            "editor",
        )
        with patch("reviewer_matching.api.get_internal_matches") as service:
            with self.assertRaises(PermissionDenied):
                internal_reviewer_matches(request, article_id=self.author_article.pk)
            service.assert_not_called()

    def test_internal_author_with_override_allowed(self):
        EditorOverride.objects.create(
            article=self.author_article,
            editor=self.author_editor,
        )
        request = self.make_internal_request(
            self.author_editor,
            self.journal_a,
            self.author_article.pk,
            "editor",
        )
        with patch(
            "reviewer_matching.api.get_internal_matches",
            return_value=[],
        ) as service:
            response = internal_reviewer_matches(
                request, article_id=self.author_article.pk
            )
            self.assertEqual(response.status_code, 200)
            service.assert_called_once()

    def test_internal_cross_journal_denied(self):
        request = self.make_internal_request(
            self.editor_a,
            self.journal_a,
            self.article_b.pk,
            "editor",
        )
        with self.assertRaises(Http404):
            internal_reviewer_matches(request, article_id=self.article_b.pk)

    def test_accepted_article_denies_combined(self):
        Article.objects.filter(pk=self.article_a.pk).update(stage=STAGE_ACCEPTED)
        request = self.make_request(self.editor_a, self.journal_a, self.article_a.pk)
        with self.assertRaises(PermissionDenied):
            self.invoke(request, self.article_a.pk)

    def test_unassigned_article_denies_combined(self):
        Article.objects.filter(pk=self.article_a.pk).update(stage=STAGE_UNASSIGNED)
        request = self.make_request(self.editor_a, self.journal_a, self.article_a.pk)
        with self.assertRaises(PermissionDenied):
            self.invoke(request, self.article_a.pk)

    def test_internal_active_reviewer_role_denied(self):
        role, _ = Role.objects.get_or_create(
            slug="reviewer",
            defaults={"name": "Reviewer"},
        )
        AccountRole.objects.get_or_create(
            user=self.editor_a,
            journal=self.journal_a,
            role=role,
        )
        request = self.make_internal_request(
            self.editor_a,
            self.journal_a,
            self.article_a.pk,
            "reviewer",
        )
        with patch("reviewer_matching.api.get_internal_matches") as service:
            with self.assertRaises(PermissionDenied):
                internal_reviewer_matches(request, article_id=self.article_a.pk)
            service.assert_not_called()

    def test_frozen_author_orcid_match(self):
        FrozenAuthor.objects.filter(
            article=self.author_article,
            author=self.author_editor,
        ).update(frozen_orcid=("https://orcid.org/0000-0002-1825-0097/"))

        self.assertEqual(
            resolve_janeway_orcid(
                self.author_article,
                "0000-0002-1825-0097",
            ),
            "article_author",
        )

    def test_linked_author_account_orcid_match(self):
        self.author_editor.orcid = "https://orcid.org/0000-0002-1825-0097"
        self.author_editor.save(update_fields=["orcid"])

        self.assertEqual(
            resolve_janeway_orcid(
                self.author_article,
                "0000-0002-1825-0097",
            ),
            "article_author",
        )

    def test_existing_janeway_account_orcid_match(self):
        self.reader.orcid = "https://orcid.org/0000-0002-1825-0097"
        self.reader.save(update_fields=["orcid"])

        self.assertEqual(
            resolve_janeway_orcid(
                self.article_a,
                "0000-0002-1825-0097",
            ),
            "existing_janeway_account",
        )

    def test_unknown_external_orcid(self):
        self.assertEqual(
            resolve_janeway_orcid(
                self.article_a,
                "0000-0002-1825-0097",
            ),
            "new_external",
        )

    def test_external_author_orcid_is_excluded(self):
        identifier = "0000-0002-1825-0097"

        FrozenAuthor.objects.filter(
            article=self.author_article,
            author=self.author_editor,
        ).update(frozen_orcid=identifier)

        candidates = [
            {
                "openalex_id": "A900",
                "name": "Excluded Author",
                "orcid": identifier,
                "orcid_status": "available",
            }
        ]

        with (
            patch(
                "reviewer_matching.combined.get_internal_matches",
                return_value=[],
            ),
            patch(
                "reviewer_matching.combined.discover_external_researchers",
                return_value=candidates,
            ),
            patch(
                "reviewer_matching.combined.fetch_public_email",
            ) as email_service,
        ):
            result = build_combined_matches(
                self.author_article,
                self.editor_a,
                public_topics=["Statistics"],
                allow_external=True,
                allow_orcid_email=True,
            )

        self.assertEqual(result["results"]["external"], [])
        self.assertEqual(result["excluded_article_authors"], 1)
        email_service.assert_not_called()

    def test_existing_janeway_account_is_identified(self):
        identifier = "0000-0002-1825-0097"

        self.reader.orcid = f"https://orcid.org/{identifier}"
        self.reader.save(update_fields=["orcid"])

        candidates = [
            {
                "openalex_id": "A901",
                "name": "Existing Researcher",
                "orcid": identifier,
                "orcid_status": "available",
            }
        ]

        with (
            patch(
                "reviewer_matching.combined.get_internal_matches",
                return_value=[],
            ),
            patch(
                "reviewer_matching.combined.discover_external_researchers",
                return_value=candidates,
            ),
            patch(
                "reviewer_matching.combined.fetch_public_email",
            ) as email_service,
        ):
            result = build_combined_matches(
                self.article_a,
                self.editor_a,
                public_topics=["Statistics"],
                allow_external=True,
                allow_orcid_email=True,
            )

        candidate = result["results"]["external"][0]

        self.assertEqual(
            candidate["identity_status"],
            "existing_janeway_account",
        )
        self.assertEqual(
            candidate["email_status"],
            "use_janeway_account",
        )
        email_service.assert_not_called()

    def test_new_external_is_not_invited_or_emailed(self):
        candidates = [
            {
                "openalex_id": "A902",
                "name": "New Researcher",
                "orcid": "0000-0002-1825-0097",
                "orcid_status": "available",
            }
        ]

        with (
            patch(
                "reviewer_matching.combined.get_internal_matches",
                return_value=[],
            ),
            patch(
                "reviewer_matching.combined.discover_external_researchers",
                return_value=candidates,
            ),
            patch(
                "reviewer_matching.combined.fetch_public_email",
            ) as email_service,
        ):
            result = build_combined_matches(
                self.article_a,
                self.editor_a,
                public_topics=["Statistics"],
                allow_external=True,
            )

        candidate = result["results"]["external"][0]

        self.assertEqual(
            candidate["identity_status"],
            "new_external",
        )
        self.assertEqual(candidate["email_status"], "disabled")
        self.assertIsNone(candidate["email"])
        self.assertFalse(candidate["invitation_ready"])
        email_service.assert_not_called()
