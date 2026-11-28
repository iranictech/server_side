from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, RequestFactory, override_settings

from identifiers.zenodo_ui import zenodo_action


class ZenodoUITests(SimpleTestCase):

    def setUp(self):
        self.factory = RequestFactory()
        self.article = SimpleNamespace(pk=40)

        # Isolate Zenodo authorization from Janeway's
        # general authentication middleware.
        auth_patcher = patch(
            "security.decorators.base_check",
            return_value=True,
        )
        auth_patcher.start()
        self.addCleanup(auth_patcher.stop)

    def request(self, action, *, method="post", superuser=True):
        url = f"/identifiers/40/zenodo/{action}/"

        if method == "post":
            request = self.factory.post(url)
        else:
            request = self.factory.get(url)

        request.journal = SimpleNamespace(pk=1)
        request.user = SimpleNamespace(
            is_authenticated=True,
            is_anonymous=False,
            is_superuser=superuser,
            is_staff=True,
            is_production=lambda request: True,
            has_senior_editor_role=lambda request: False,
        )
        return request

    @override_settings(ZENODO_SANDBOX_UI_ENABLED=False)
    def test_disabled_ui_blocks_remote_operations(self):
        with (
            patch(
                "identifiers.zenodo_ui.get_object_or_404",
                return_value=self.article,
            ),
            patch(
                "identifiers.zenodo_ui.ZenodoDeposit.objects.filter"
            ) as query,
        ):
            for action in (
                "prepare", "create", "upload",
                "check", "reconcile",
            ):
                with self.subTest(action=action):
                    response = zenodo_action.__wrapped__(
                        self.request(action),
                        article_id=40,
                        action=action,
                    )
                    self.assertEqual(response.status_code, 403)

            query.assert_not_called()

    @override_settings(ZENODO_SANDBOX_UI_ENABLED=True)
    def test_non_superuser_is_blocked(self):
        with patch(
            "identifiers.zenodo_ui.get_object_or_404",
            return_value=self.article,
        ):
            response = zenodo_action.__wrapped__(
                self.request("create", superuser=False),
                article_id=40,
                action="create",
            )

        self.assertEqual(response.status_code, 403)
