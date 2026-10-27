"""Regression tests for journal-scoped active-role authorization."""

from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse

from core import models as core_models
from core.middleware import ActiveRoleMiddleware
from security import decorators
from submission import models as submission_models
from utils.testing import helpers


class TestActiveRoleAuthorization(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.journal, cls.other_journal = helpers.create_journals()
        helpers.create_roles(
            ["author", "editor", "reader", "journal-manager", "reviewer"]
        )
        cls.user = helpers.create_user(
            "active.roles@example.org",
            ["author", "editor", "reader", "journal-manager"],
            journal=cls.journal,
        )
        cls.user.is_active = True
        cls.user.save()
        cls.article = helpers.create_article(cls.journal)
        cls.author_record = helpers.create_frozen_author(cls.article)

    def request_for(self, role, journal=None):
        request = RequestFactory().get("/test-active-role/")
        request.user = self.user
        request.journal = journal or self.journal
        request.active_role_slug = role
        return request

    def test_only_the_selected_assigned_role_is_effective(self):
        editor_request = self.request_for("editor")
        self.assertTrue(self.user.is_editor(editor_request))
        self.assertFalse(self.user.is_author(editor_request))
        self.assertFalse(self.user.is_reader(editor_request))

        author_request = self.request_for("author")
        self.assertTrue(self.user.is_author(author_request))
        self.assertFalse(self.user.is_editor(author_request))
        self.assertFalse(
            self.user.has_active_role(
                author_request, "journal-manager", staff_override=False
            )
        )

    def test_selected_role_is_verified_against_journal_membership(self):
        self.assertFalse(self.user.is_reviewer(self.request_for("reviewer")))
        self.assertFalse(
            self.user.is_editor(
                self.request_for("editor", journal=self.other_journal)
            )
        )

    def test_editor_membership_cannot_edit_as_author(self):
        article = self.article
        author_record = self.author_record

        self.assertTrue(article.can_edit(self.user, request=self.request_for("editor")))
        self.assertFalse(article.can_edit(self.user, request=self.request_for("author")))
        self.assertTrue(
            author_record.can_edit(self.user, request=self.request_for("editor"))
        )
        self.assertFalse(
            author_record.can_edit(self.user, request=self.request_for("author"))
        )

        # Membership checks remain usable by background operations without
        # a request; request-bound web actions must use the active role.
        self.assertTrue(article.can_edit(self.user))

    def test_editor_decorator_denies_inactive_editor_and_manager_roles(self):
        guarded = decorators.editor_user_required(
            lambda request: HttpResponse("allowed")
        )
        with self.assertRaises(PermissionDenied):
            guarded(self.request_for("author"))
        self.assertEqual(guarded(self.request_for("editor")).status_code, 200)

    def test_article_edit_decorator_checks_active_role(self):
        guarded = decorators.user_can_edit_article(
            lambda request, article_id: HttpResponse("allowed")
        )
        with self.assertRaises(PermissionDenied):
            guarded(self.request_for("author"), article_id=self.article.pk)
        self.assertEqual(
            guarded(self.request_for("editor"), article_id=self.article.pk).status_code,
            200,
        )

    def test_unsubmitted_owner_cannot_edit_as_unrelated_role(self):
        self.article.owner = self.user
        self.article.stage = submission_models.STAGE_UNSUBMITTED
        self.article.save()
        self.assertTrue(
            self.article.can_edit(self.user, request=self.request_for("author"))
        )
        self.assertFalse(
            self.article.can_edit(self.user, request=self.request_for("reader"))
        )

    def test_removed_active_role_is_revalidated_on_each_request(self):
        request = self.request_for("editor")
        request.session = {
            ActiveRoleMiddleware.SESSION_KEY: {str(self.journal.pk): "editor"}
        }
        core_models.AccountRole.objects.filter(
            user=self.user, journal=self.journal, role__slug="editor"
        ).delete()

        ActiveRoleMiddleware.process_request(request)

        self.assertNotEqual(request.active_role_slug, "editor")
        self.assertFalse(self.user.is_editor(request))
        self.assertIn(
            request.active_role_slug,
            {"author", "reader", "journal-manager"},
        )

    def test_switch_role_accepts_post_for_assigned_roles_only(self):
        self.client.force_login(self.user)
        url = reverse("core_switch_active_role", kwargs={"role_slug": "editor"})
        response = self.client.post(url, SERVER_NAME=self.journal.domain)
        self.assertEqual(response.status_code, 302)
        roles = self.client.session["janeway_active_roles"]
        self.assertEqual(roles[str(self.journal.pk)], "editor")

        self.assertEqual(
            self.client.get(url, SERVER_NAME=self.journal.domain).status_code,
            405,
        )
        invalid_url = reverse(
            "core_switch_active_role", kwargs={"role_slug": "reviewer"}
        )
        self.assertEqual(
            self.client.post(
                invalid_url, SERVER_NAME=self.journal.domain
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.session["janeway_active_roles"][str(self.journal.pk)],
            "editor",
        )
