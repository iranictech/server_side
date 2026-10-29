from types import SimpleNamespace

from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.test import RequestFactory, TestCase

from core.middleware import ActiveRoleMiddleware
from core.views import switch_active_role
from security.decorators import editor_user_required
from security.logic import can_edit_file, can_view_file
from utils.testing import helpers


class EditorInChiefPortTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        helpers.create_press()
        cls.journal_one, cls.journal_two = helpers.create_journals()
        helpers.create_roles(["author", "editor", "editor-in-chief"])

        cls.eic = helpers.create_user(
            "eic-port@example.com",
            ["author", "editor-in-chief"],
            journal=cls.journal_one,
            is_active=True,
        )
        cls.outsider = helpers.create_user(
            "outsider-port@example.com",
            ["author"],
            journal=cls.journal_two,
            is_active=True,
        )

    def setUp(self):
        self.factory = RequestFactory()

    def request(self, role="editor-in-chief", journal=None, user=None,
                method="get", data=None):
        url = "/role/editor-in-chief/switch/"
        if method == "post":
            request = self.factory.post(url, data or {})
        else:
            request = self.factory.get(url)

        request.user = user if user is not None else self.eic
        request.journal = journal if journal is not None else self.journal_one
        request.repository = None
        request.active_role_slug = role
        request.session = {}
        return request

    def test_eic_role_has_editorial_authority(self):
        request = self.request()
        self.assertTrue(self.eic.is_editor_in_chief(request))
        self.assertTrue(self.eic.has_senior_editor_role(request))
        self.assertTrue(self.eic.has_an_editor_role(request))

    def test_author_active_role_has_no_editorial_authority(self):
        request = self.request(role="author")
        self.assertFalse(self.eic.is_editor_in_chief(request))
        self.assertFalse(self.eic.has_senior_editor_role(request))

    def test_eic_not_implicitly_journal_manager(self):
        self.assertFalse(self.eic.is_journal_manager(self.journal_one))
        self.assertFalse(self.eic.is_staff)
        self.assertFalse(self.eic.is_superuser)

    def test_eic_cannot_cross_journals(self):
        request = self.request(journal=self.journal_two)
        self.assertFalse(self.eic.is_editor_in_chief(request))
        self.assertFalse(self.eic.has_senior_editor_role(request))

    def test_forged_active_role_does_not_grant_access(self):
        request = self.request(user=self.outsider)
        self.assertFalse(self.outsider.is_editor_in_chief(request))

    def test_editor_decorator_allows_active_eic(self):
        view = editor_user_required(lambda r: HttpResponse("OK"))
        response = view(self.request())
        self.assertEqual(response.status_code, 200)

    def test_editor_decorator_blocks_active_author(self):
        view = editor_user_required(lambda r: HttpResponse("OK"))
        with self.assertRaises(PermissionDenied):
            view(self.request(role="author"))

    def test_editor_decorator_blocks_other_journal(self):
        view = editor_user_required(lambda r: HttpResponse("OK"))
        with self.assertRaises(PermissionDenied):
            view(self.request(journal=self.journal_two))

    def test_switch_role_post(self):
        request = self.request(
            role="author",
            method="post",
            data={"next": "/dashboard/"},
        )
        response = switch_active_role(request, "editor-in-chief")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            request.session["janeway_active_roles"][str(self.journal_one.pk)],
            "editor-in-chief",
        )

    def test_switch_role_cannot_assign_foreign_role(self):
        request = self.request(
            journal=self.journal_two,
            method="post",
        )
        with self.assertRaises(Http404):
            switch_active_role(request, "editor-in-chief")

    def test_switch_role_rejects_get(self):
        response = switch_active_role(self.request(method="get"), "editor-in-chief")
        self.assertEqual(response.status_code, 405)

    def test_middleware_selects_existing_role(self):
        request = self.request(role=None)
        request.session = {
            "janeway_active_roles": {
                str(self.journal_one.pk): "editor-in-chief"
            }
        }
        ActiveRoleMiddleware.process_request(request)
        self.assertEqual(request.active_role_slug, "editor-in-chief")

    def test_middleware_rejects_forged_selection(self):
        request = self.request(role=None)
        request.session = {
            "janeway_active_roles": {
                str(self.journal_one.pk): "journal-manager"
            }
        }
        ActiveRoleMiddleware.process_request(request)
        self.assertNotEqual(request.active_role_slug, "journal-manager")

    def test_eic_can_edit_file_in_own_journal(self):
        article = SimpleNamespace(pk=101, journal=self.journal_one)
        file_obj = SimpleNamespace(
            article_id=101, article=article, owner=None, privacy="editors"
        )
        self.assertTrue(
            can_edit_file(self.request(), self.eic, file_obj, article)
        )

    def test_eic_cannot_edit_file_in_other_journal(self):
        article = SimpleNamespace(pk=102, journal=self.journal_two)
        file_obj = SimpleNamespace(
            article_id=102, article=article, owner=None, privacy="editors"
        )
        self.assertFalse(
            can_edit_file(self.request(), self.eic, file_obj, article)
        )

    def test_eic_cannot_edit_mismatched_article_file(self):
        article = SimpleNamespace(pk=101, journal=self.journal_one)
        file_obj = SimpleNamespace(
            article_id=999, article=article, owner=None, privacy="editors"
        )
        self.assertFalse(
            can_edit_file(self.request(), self.eic, file_obj, article)
        )

    def test_eic_cannot_view_other_journal_private_file(self):
        article = SimpleNamespace(pk=102, journal=self.journal_two)
        file_obj = SimpleNamespace(
            article_id=102, article=article, owner=None, privacy="editors"
        )
        self.assertFalse(
            can_view_file(self.request(), self.eic, file_obj)
        )

    def test_eic_cannot_view_private_unbound_file(self):
        file_obj = SimpleNamespace(
            article_id=None,
            article=None,
            owner=None,
            privacy="editors",
        )
        self.assertFalse(
            can_view_file(self.request(), self.eic, file_obj)
        )
