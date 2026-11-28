from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, RequestFactory, override_settings

from identifiers.zenodo_ui import zenodo_action


@override_settings(ZENODO_SANDBOX_UI_ENABLED=True)
class ZenodoDashboardActionTests(SimpleTestCase):

    def setUp(self):
        self.factory = RequestFactory()
        self.article = SimpleNamespace(pk=40)
        self.deposit = SimpleNamespace(pk=7)

        auth = patch(
            "security.decorators.base_check",
            return_value=True,
        )
        auth.start()
        self.addCleanup(auth.stop)

    def request(self, action, data=None):
        request = self.factory.post(
            f"/identifiers/40/zenodo/{action}/",
            data=data or {},
        )
        request.journal = SimpleNamespace(pk=1)
        request.user = SimpleNamespace(
            is_authenticated=True,
            is_anonymous=False,
            is_active=True,
            is_superuser=True,
            is_staff=True,
            is_production=lambda request: True,
            has_senior_editor_role=lambda request: False,
        )
        return request

    def execute(self, action, deposit, data=None):
        with (
            patch(
                "identifiers.zenodo_ui.get_object_or_404",
                return_value=self.article,
            ),
            patch(
                "identifiers.zenodo_ui.ZenodoDeposit.objects.filter"
            ) as queryset,
            patch("identifiers.zenodo_ui.messages"),
            patch(
                "identifiers.zenodo_sandbox.ZenodoSandboxClient"
            ) as client_class,
        ):
            queryset.return_value.first.return_value = deposit

            response = zenodo_action.__wrapped__(
                self.request(action, data),
                article_id=40,
                action=action,
            )

        return response, client_class

    def test_prepare(self):
        with patch(
            "identifiers.zenodo_workflow.begin_sandbox_deposit"
        ) as operation:
            response, client = self.execute("prepare", None)

        self.assertEqual(response.status_code, 302)
        operation.assert_called_once_with(40)
        client.assert_not_called()

    def test_create(self):
        with patch(
            "identifiers.zenodo_workflow.create_sandbox_remote_draft"
        ) as operation:
            response, client = self.execute(
                "create", self.deposit
            )

        self.assertEqual(response.status_code, 302)
        operation.assert_called_once_with(
            7, client.return_value
        )

    def test_upload(self):
        with patch(
            "identifiers.zenodo_upload_workflow."
            "upload_sandbox_article_pdf"
        ) as operation:
            response, client = self.execute(
                "upload", self.deposit
            )

        self.assertEqual(response.status_code, 302)
        operation.assert_called_once_with(
            7, client.return_value
        )

    def test_check(self):
        with patch(
            "identifiers.zenodo_recovery."
            "inspect_known_sandbox_deposit",
            return_value={"remote_deposition_id": 124},
        ) as operation:
            response, client = self.execute(
                "check", self.deposit
            )

        self.assertEqual(response.status_code, 302)
        operation.assert_called_once_with(
            7, client.return_value
        )

    def test_reconcile(self):
        with patch(
            "identifiers.zenodo_upload_reconcile."
            "reconcile_sandbox_pdf_upload",
            return_value={"changed": True},
        ) as operation:
            response, client = self.execute(
                "reconcile",
                self.deposit,
                {"confirm": "yes"},
            )

        self.assertEqual(response.status_code, 302)
        operation.assert_called_once_with(
            7, client.return_value, confirmed=True
        )

    def test_reconcile_without_confirmation(self):
        with patch(
            "identifiers.zenodo_upload_reconcile."
            "reconcile_sandbox_pdf_upload"
        ) as operation:
            response, client = self.execute(
                "reconcile", self.deposit
            )

        self.assertEqual(response.status_code, 403)
        operation.assert_not_called()
        client.assert_called_once()
