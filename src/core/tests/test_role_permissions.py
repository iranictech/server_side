from unittest.mock import patch

from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase
from django.http import HttpResponse
from django.db import transaction

from core import models
from core.role_permissions import (
    update_role_permissions,
    get_role_permission_context,
)
from utils import setting_handler
from utils.testing import helpers


class RolePermissionsTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        helpers.create_press()
        cls.journal_one, cls.journal_two = helpers.create_journals()

        for slug in ("editor", "journal-manager", "editor-in-chief"):
            models.Role.objects.get_or_create(
                slug=slug,
                defaults={"name": slug.replace("-", " ").title()},
            )

        cls.manager = helpers.create_user(
            "manager-permissions@example.com",
            roles=["journal-manager"],
            journal=cls.journal_one,
        )
        cls.editor = helpers.create_user(
            "editor-permissions@example.com",
            roles=["editor"],
            journal=cls.journal_one,
        )
        cls.regular = helpers.create_user(
            "regular-permissions@example.com",
        )

        group, _ = models.SettingGroup.objects.get_or_create(
            name="permission"
        )

        for name in ("sections", "licenses"):
            setting, _ = models.Setting.objects.get_or_create(
                group=group,
                name=name,
                defaults={"types": "json"},
            )
            models.SettingValue.objects.update_or_create(
                setting=setting,
                journal=None,
                defaults={
                    "value": '["editor", "journal-manager"]'
                },
            )

    def setUp(self):
        self.factory = RequestFactory()
        self.url = "/manager/roles/editor-in-chief/permissions/"

    def make_request(self, user, data=None, method="post", journal=None):
        if method == "post":
            request = self.factory.post(self.url, data or {})
        else:
            request = self.factory.get(self.url)

        request.user = user
        request.journal = journal or self.journal_one
        return request

    def test_editor_cannot_update_permissions(self):
        request = self.make_request(
            self.editor, {"sections": "on"}
        )
        with self.assertRaises(PermissionDenied):
            update_role_permissions(
                request, slug="editor-in-chief"
            )

    def test_regular_user_cannot_update_permissions(self):
        request = self.make_request(
            self.regular, {"sections": "on"}
        )
        with self.assertRaises(PermissionDenied):
            update_role_permissions(
                request, slug="editor-in-chief"
            )

    def test_get_request_is_rejected(self):
        request = self.make_request(
            self.manager, method="get"
        )
        response = update_role_permissions(
            request, slug="editor-in-chief"
        )
        self.assertEqual(response.status_code, 405)

    @patch("core.role_permissions.messages.success")
    def test_manager_can_update_permissions(self, _message):
        request = self.make_request(
            self.manager,
            {"sections": "on", "licenses": "on"},
        )

        response = update_role_permissions(
            request, slug="editor-in-chief"
        )

        self.assertEqual(response.status_code, 302)

        setting = setting_handler.get_setting(
            "permission", "sections", self.journal_one
        )

        self.assertIn(
            "editor-in-chief", setting.processed_value
        )
        self.assertIn("editor", setting.processed_value)
        self.assertIn(
            "journal-manager", setting.processed_value
        )

    @patch("core.role_permissions.messages.success")
    def test_journal_isolation(self, _message):
        request = self.make_request(
            self.manager,
            {"sections": "on"},
        )

        update_role_permissions(
            request, slug="editor-in-chief"
        )

        first = setting_handler.get_setting(
            "permission", "sections", self.journal_one
        )
        second = setting_handler.get_setting(
            "permission", "sections", self.journal_two
        )

        self.assertIn(
            "editor-in-chief", first.processed_value
        )
        self.assertNotIn(
            "editor-in-chief", second.processed_value
        )

    def test_invalid_input_does_not_save(self):
        request = self.make_request(
            self.manager,
            {"sections": "on", "licenses": "invalid"},
        )

        with self.assertRaises(PermissionDenied):
            update_role_permissions(
                request, slug="editor-in-chief"
            )

        self.assertFalse(
            models.SettingValue.objects.filter(
                journal=self.journal_one,
                setting__name="sections",
                setting__group__name="permission",
            ).exists()
        )

    def test_manager_cannot_update_other_journal(self):
        request = self.make_request(
            self.manager,
            {"sections": "on", "licenses": "on"},
            journal=self.journal_two,
        )

        with self.assertRaises(PermissionDenied):
            update_role_permissions(
                request, slug="editor-in-chief"
            )

        self.assertFalse(
            models.SettingValue.objects.filter(
                journal=self.journal_two,
                setting__name="sections",
                setting__group__name="permission",
            ).exists()
        )

    def test_manager_cannot_modify_other_roles(self):
        request = self.make_request(
            self.manager,
            {"sections": "on", "licenses": "on"},
        )

        with self.assertRaises(PermissionDenied):
            update_role_permissions(
                request, slug="editor"
            )

        self.assertFalse(
            models.SettingValue.objects.filter(
                journal=self.journal_one,
                setting__name="sections",
                setting__group__name="permission",
            ).exists()
        )

    @patch("core.role_permissions.messages.success")
    def test_staff_can_update_permissions(self, _message):
        self.regular.is_staff = True
        self.regular.save(update_fields=["is_staff"])

        request = self.make_request(
            self.regular,
            {"sections": "on", "licenses": "on"},
        )

        response = update_role_permissions(
            request, slug="editor-in-chief"
        )

        self.assertEqual(response.status_code, 302)

        for name in ("sections", "licenses"):
            setting = setting_handler.get_setting(
                "permission", name, self.journal_one
            )
            self.assertIn(
                "editor-in-chief", setting.processed_value
            )

    def test_editor_cannot_manage_context(self):
        role = models.Role.objects.get(
            slug="editor-in-chief"
        )
        request = self.make_request(self.editor)

        context = get_role_permission_context(
            request, role
        )

        self.assertFalse(
            context["can_manage_role_permissions"]
        )
