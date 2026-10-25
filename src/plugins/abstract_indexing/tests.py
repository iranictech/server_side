from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from unittest.mock import Mock, patch
from django.test import RequestFactory, SimpleTestCase

from plugins.abstract_indexing.views import abstract_indexing_config


class AbstractIndexingSecurityTests(SimpleTestCase):
    def test_config_rejects_request_without_journal(self):
        request = RequestFactory().get("/plugins/abstract-indexing/")
        request.journal = None

        with self.assertRaises(Http404):
            abstract_indexing_config(request)

    def test_config_redirects_anonymous_user(self):
        request = RequestFactory().get("/plugins/abstract-indexing/")
        request.journal = Mock(pk=1)
        request.user = AnonymousUser()

        response = abstract_indexing_config(request)

        self.assertEqual(response.status_code, 302)
        self.assertIn("next=", response.url)

    def test_config_redirects_inactive_user(self):
        request = RequestFactory().get("/plugins/abstract-indexing/")
        request.journal = Mock(pk=1)
        request.user = type(
            "InactiveUser",
            (),
            {"is_anonymous": False, "is_active": False},
        )()

        response = abstract_indexing_config(request)

        self.assertEqual(response.status_code, 302)
        self.assertIn("next=", response.url)

    def make_role_request(self, is_editor=False, is_manager=False):
        request = RequestFactory().get("/plugins/abstract-indexing/")
        request.journal = Mock(pk=1)
        request.user = Mock()
        request.user.is_anonymous = False
        request.user.is_active = True
        request.user.is_editor.return_value = is_editor
        request.user.is_journal_manager.return_value = is_manager
        return request

    def test_config_blocks_author(self):
        request = self.make_role_request()

        with patch("security.decorators.deny_access", side_effect=PermissionDenied):
            with self.assertRaises(PermissionDenied):
                abstract_indexing_config(request)

    def test_config_allows_editor(self):
        request = self.make_role_request(is_editor=True)

        with patch(
                "plugins.abstract_indexing.views.render",
                return_value=HttpResponse("OK"),
        ) as mocked_render:
            with patch(
                    "plugins.abstract_indexing.views.AbstractIndexing.objects.filter"
            ) as filtered:
                with patch(
                        "django.contrib.contenttypes.models.ContentType.objects.get_for_model"
                ) as get_content_type:
                    with patch(
                            "core.models.HomepageElement.objects.filter"
                    ) as homepage_filter:
                        filtered.return_value.order_by.return_value = []
                        get_content_type.return_value = Mock(pk=10)
                        homepage_filter.return_value.exists.return_value = False

                        response = abstract_indexing_config(request)

        self.assertEqual(response.status_code, 200)

        filtered.assert_called_once_with(
            journal=request.journal,
        )

        get_content_type.assert_called_once_with(
            request.journal,
        )

        homepage_filter.assert_called_once_with(
            name="Abstract Indexing",
            content_type=get_content_type.return_value,
            object_id=request.journal.pk,
        )

        context = mocked_render.call_args.args[2]
        self.assertFalse(context["homepage_registered"])

    def test_config_blocks_editor_of_other_journal(self):
        request = self.make_role_request()

        with patch("security.decorators.deny_access", side_effect=PermissionDenied):
            with self.assertRaises(PermissionDenied):
                abstract_indexing_config(request)


from django.test import TestCase
from utils.testing import helpers


class AbstractIndexingIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.journal_one, cls.journal_two = helpers.create_journals()
        helpers.create_roles(["author", "editor", "journal-manager"])

        cls.author = helpers.create_user(
            "index-author@example.com",
            ["author"],
            journal=cls.journal_one,
            is_active=True,
        )
        cls.editor = helpers.create_user(
            "index-editor@example.com",
            ["editor"],
            journal=cls.journal_one,
            is_active=True,
        )
        cls.manager = helpers.create_user(
            "index-manager@example.com",
            ["journal-manager"],
            journal=cls.journal_one,
            is_active=True,
        )
        cls.other_editor = helpers.create_user(
            "index-other-editor@example.com",
            ["editor"],
            journal=cls.journal_two,
            is_active=True,
        )

    def make_request(self, user):
        request = RequestFactory().get("/plugins/abstract-indexing/")
        request.user = user
        request.journal = self.journal_one
        return request

    def test_author_denied(self):
        request = self.make_request(self.author)

        with self.assertRaises(PermissionDenied):
            abstract_indexing_config(request)

    def test_editor_allowed(self):
        request = self.make_request(self.editor)

        with patch(
            "plugins.abstract_indexing.views.render",
            return_value=HttpResponse("OK"),
        ):
            response = abstract_indexing_config(request)

        self.assertEqual(response.status_code, 200)

    def test_journal_manager_allowed(self):
        request = self.make_request(self.manager)

        with patch(
            "plugins.abstract_indexing.views.render",
            return_value=HttpResponse("OK"),
        ):
            response = abstract_indexing_config(request)

        self.assertEqual(response.status_code, 200)

    def test_other_journal_editor_denied(self):
        request = self.make_request(self.other_editor)

        with self.assertRaises(PermissionDenied):
            abstract_indexing_config(request)


    def test_cannot_edit_other_journal_indexing(self):
        from plugins.abstract_indexing.models import AbstractIndexing
        from plugins.abstract_indexing.views import abstract_indexing_edit

        record = AbstractIndexing.objects.create(
            journal=self.journal_two,
            name="Other Journal Index",
        )

        request = self.make_request(self.editor)

        with self.assertRaises(Http404):
            abstract_indexing_edit(request, pk=record.pk)

        self.assertTrue(
            AbstractIndexing.objects.filter(pk=record.pk).exists()
        )

    def test_cannot_delete_other_journal_indexing(self):
        from plugins.abstract_indexing.models import AbstractIndexing
        from plugins.abstract_indexing.views import abstract_indexing_delete

        record = AbstractIndexing.objects.create(
            journal=self.journal_two,
            name="Protected Journal Index",
        )

        request = RequestFactory().post("/plugins/abstract-indexing/delete/")
        request.user = self.editor
        request.journal = self.journal_one

        with self.assertRaises(Http404):
            abstract_indexing_delete(request, pk=record.pk)

        self.assertTrue(
            AbstractIndexing.objects.filter(pk=record.pk).exists()
        )


    def test_get_request_does_not_delete_indexing(self):
        from plugins.abstract_indexing.models import AbstractIndexing
        from plugins.abstract_indexing.views import abstract_indexing_delete

        record = AbstractIndexing.objects.create(
            journal=self.journal_one,
            name="Index Protected From GET",
        )

        request = self.make_request(self.editor)

        with patch(
            "plugins.abstract_indexing.views.redirect",
            return_value=HttpResponse(status=302),
        ):
            response = abstract_indexing_delete(request, pk=record.pk)

        self.assertEqual(response.status_code, 405)
        self.assertTrue(
            AbstractIndexing.objects.filter(pk=record.pk).exists()
        )


    def test_public_indexing_filters_by_journal_and_active_status(self):
        from plugins.abstract_indexing.models import AbstractIndexing
        from plugins.abstract_indexing.views import indexing

        visible = AbstractIndexing.objects.create(
            journal=self.journal_one,
            name="Visible Index",
            ordering=2,
            is_active=True,
        )
        first = AbstractIndexing.objects.create(
            journal=self.journal_one,
            name="First Index",
            ordering=1,
            is_active=True,
        )
        AbstractIndexing.objects.create(
            journal=self.journal_one,
            name="Inactive Index",
            is_active=False,
        )
        AbstractIndexing.objects.create(
            journal=self.journal_two,
            name="Other Journal Index",
            is_active=True,
        )

        request = self.make_request(self.editor)

        with patch("plugins.abstract_indexing.views.render") as mocked_render:
            indexing(request)

        context = mocked_render.call_args.args[2]
        results = list(context["indexings"])

        self.assertEqual(results, [first, visible])
        self.assertEqual(
            mocked_render.call_args.args[1],
            "journal/indexing.html",
        )



    def make_register_request(self, user, journal=None, method="post"):
        from django.contrib.messages.storage.fallback import FallbackStorage

        factory = RequestFactory()
        path = "/plugins/abstract-indexing/register-homepage/"
        request = factory.post(path) if method == "post" else factory.get(path)
        request.user = user
        request.journal = journal if journal is not None else self.journal_one
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    def test_register_homepage_only_for_current_journal(self):
        from django.contrib.contenttypes.models import ContentType
        from core.models import HomepageElement
        from plugins.abstract_indexing.views import abstract_indexing_register_homepage

        request = self.make_register_request(self.editor)
        with patch(
            "plugins.abstract_indexing.views.redirect",
            return_value=HttpResponse(status=302),
        ):
            response = abstract_indexing_register_homepage(request)

        content_type = ContentType.objects.get_for_model(self.journal_one)
        element = HomepageElement.objects.get(
            name="Abstract Indexing",
            content_type=content_type,
            object_id=self.journal_one.pk,
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(element.active)
        self.assertFalse(
            HomepageElement.objects.filter(
                name="Abstract Indexing",
                content_type=content_type,
                object_id=self.journal_two.pk,
            ).exists()
        )

    def test_register_homepage_does_not_create_duplicates(self):
        from django.contrib.contenttypes.models import ContentType
        from core.models import HomepageElement
        from plugins.abstract_indexing.views import abstract_indexing_register_homepage

        request = self.make_register_request(self.editor)
        with patch(
            "plugins.abstract_indexing.views.redirect",
            return_value=HttpResponse(status=302),
        ):
            abstract_indexing_register_homepage(request)
            abstract_indexing_register_homepage(request)

        self.assertEqual(
            HomepageElement.objects.filter(
                name="Abstract Indexing",
                content_type=ContentType.objects.get_for_model(self.journal_one),
                object_id=self.journal_one.pk,
            ).count(),
            1,
        )

    def test_register_homepage_preserves_active_state(self):
        from django.contrib.contenttypes.models import ContentType
        from core.models import HomepageElement
        from plugins.abstract_indexing.views import abstract_indexing_register_homepage

        element = HomepageElement.objects.create(
            name="Abstract Indexing",
            content_type=ContentType.objects.get_for_model(self.journal_one),
            object_id=self.journal_one.pk,
            configure_url="abstract_indexing_config",
            template_path="journal/homepage_elements/indexing.html",
            active=True,
        )
        request = self.make_register_request(self.editor)
        with patch(
            "plugins.abstract_indexing.views.redirect",
            return_value=HttpResponse(status=302),
        ):
            abstract_indexing_register_homepage(request)

        element.refresh_from_db()
        self.assertTrue(element.active)

    def test_register_homepage_rejects_get(self):
        from plugins.abstract_indexing.views import abstract_indexing_register_homepage

        request = self.make_register_request(self.editor, method="get")
        response = abstract_indexing_register_homepage(request)
        self.assertEqual(response.status_code, 405)

    def test_register_homepage_blocks_author(self):
        from plugins.abstract_indexing.views import abstract_indexing_register_homepage

        request = self.make_register_request(self.author)
        with self.assertRaises(PermissionDenied):
            abstract_indexing_register_homepage(request)

    def test_register_homepage_blocks_other_journal_editor(self):
        from plugins.abstract_indexing.views import abstract_indexing_register_homepage

        request = self.make_register_request(self.other_editor)
        with self.assertRaises(PermissionDenied):
            abstract_indexing_register_homepage(request)


class AbstractIndexingPublicRoutingTests(SimpleTestCase):

    def setUp(self):
        self.factory = RequestFactory()

    def make_request(self, journal=None):
        request = self.factory.get("/indexing/")
        request.journal = journal
        return request

    def test_public_view_returns_404_without_journal(self):
        from django.http import Http404
        from journal.views import abstract_indexing_public_view

        request = self.make_request()

        with self.assertRaises(Http404):
            abstract_indexing_public_view(request)

    def test_public_view_returns_404_when_plugin_disabled(self):
        from django.http import Http404
        from journal.views import abstract_indexing_public_view

        request = self.make_request(journal=object())

        with patch("core.plugin_loader.get_plugin", return_value=False):
            with self.assertRaises(Http404):
                abstract_indexing_public_view(request)

    def test_public_view_delegates_when_plugin_enabled(self):
        from journal.views import abstract_indexing_public_view

        request = self.make_request(journal=object())
        expected = HttpResponse("Indexing page")

        with patch("core.plugin_loader.get_plugin", return_value=True) as check:
            with patch(
                "plugins.abstract_indexing.views.indexing",
                return_value=expected,
            ) as public_view:
                response = abstract_indexing_public_view(request)

        self.assertIs(response, expected)
        check.assert_called_once_with(
            "abstract_indexing",
            permissive=False,
        )
        public_view.assert_called_once_with(request)


    def test_public_view_returns_404_when_plugin_module_missing(self):
        import builtins
        from django.http import Http404
        from journal.views import abstract_indexing_public_view

        request = self.make_request(journal=object())
        original_import = builtins.__import__

        def simulate_missing_plugin(name, *args, **kwargs):
            if name == "plugins.abstract_indexing.views":
                raise ModuleNotFoundError(
                    "No module named 'plugins.abstract_indexing.views'",
                    name="plugins.abstract_indexing.views",
                )
            return original_import(name, *args, **kwargs)

        with patch("core.plugin_loader.get_plugin", return_value=True):
            with patch("builtins.__import__", side_effect=simulate_missing_plugin):
                with self.assertRaises(Http404):
                    abstract_indexing_public_view(request)


class AbstractIndexingInstallationTests(TestCase):

    def test_install_does_not_modify_homepage_elements(self):
        from core.models import HomepageElement
        from plugins.abstract_indexing.plugin_settings import install

        journal_one, journal_two = helpers.create_journals()

        before = list(
            HomepageElement.objects.order_by("pk").values()
        )

        install()

        after = list(
            HomepageElement.objects.order_by("pk").values()
        )

        self.assertEqual(before, after)

    def test_install_preserves_existing_disabled_state(self):
        from plugins.abstract_indexing.plugin_settings import install
        from utils.models import Plugin

        plugin = Plugin.objects.create(
            name="abstract_indexing",
            version="1.0",
            enabled=False,
        )

        install()

        plugin.refresh_from_db()
        self.assertFalse(plugin.enabled)
