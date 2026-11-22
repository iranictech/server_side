"""Network-free tests for the Zenodo Sandbox client.

Run with: python manage.py test identifiers.tests.test_zenodo_sandbox
"""
from io import BytesIO
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from identifiers.zenodo_sandbox import (
    DEPOSITIONS_URL, Draft, ZenodoError, ZenodoSandboxClient,
    journal_article_metadata,
)


def response(payload, status=201):
    result = Mock()
    result.status_code = status
    result.json.return_value = payload
    return result


class ZenodoSandboxTests(SimpleTestCase):
    def setUp(self):
        self.session = Mock()
        self.client = ZenodoSandboxClient(token="sandbox-test-only", session=self.session)
        self.payload = {
            "id": 124,
            "metadata": {"prereserve_doi": {"doi": "10.5072/zenodo.124"}},
            "links": {
                "bucket": "https://sandbox.zenodo.org/api/files/example",
                "html": "https://sandbox.zenodo.org/deposit/124",
            },
        }

    def test_metadata_requires_title_creators_description(self):
        with self.assertRaises(ValueError):
            journal_article_metadata(title="", creators=[{"name": "Doe, Jane"}], description="Abstract")
        with self.assertRaises(ValueError):
            journal_article_metadata(title="Article", creators=[], description="Abstract")
        metadata = journal_article_metadata(
            title="Article", creators=[{"name": "Doe, Jane"}],
            description="Abstract", publication_date="2026-11-22"
        )
        self.assertTrue(metadata["prereserve_doi"])
        self.assertEqual(metadata["publication_type"], "article")

    def test_create_draft_reserves_doi_without_publishing(self):
        self.session.request.return_value = response(self.payload)
        draft = self.client.create_draft(journal_article_metadata(
            title="Article", creators=[{"name": "Doe, Jane"}], description="Abstract"
        ))
        self.assertEqual(draft.reserved_doi, "10.5072/zenodo.124")
        args, kwargs = self.session.request.call_args
        self.assertEqual(args[:2], ("POST", DEPOSITIONS_URL))
        self.assertIn("Authorization", kwargs["headers"])
        self.assertNotIn("access_token", args[1])
        self.assertFalse(kwargs["allow_redirects"])
        self.assertEqual(self.session.request.call_count, 1)

    def test_wrong_host_bucket_is_blocked(self):
        payload = dict(self.payload)
        payload["links"] = dict(self.payload["links"])
        payload["links"]["bucket"] = "https://attacker.example/api/files/steal"
        self.session.request.return_value = response(payload)
        with self.assertRaises(ZenodoError):
            self.client.create_draft({"prereserve_doi": True})

    def test_external_redirect_not_followed(self):
        self.session.request.return_value = response({}, status=302)
        with self.assertRaises(ZenodoError):
            self.client.create_draft({"prereserve_doi": True})
        self.assertFalse(self.session.request.call_args.kwargs["allow_redirects"])

    def test_error_does_not_leak_token_or_server_body(self):
        result = response({"error": "some private value"}, status=403)
        result.text = "some private value"
        self.session.request.return_value = result
        with self.assertRaises(ZenodoError) as caught:
            self.client.create_draft({"prereserve_doi": True})
        self.assertNotIn("sandbox-test-only", str(caught.exception))
        self.assertNotIn("some private value", str(caught.exception))

    def test_upload_pdf_uses_bucket(self):
        draft = Draft(124, "10.5072/zenodo.124",
                      "https://sandbox.zenodo.org/api/files/example",
                      "https://sandbox.zenodo.org/deposit/124")
        self.session.request.return_value = response({"key": "paper.pdf"}, status=200)
        self.client.upload_pdf(draft, BytesIO(b"%PDF-test"), "paper.pdf")
        args, kwargs = self.session.request.call_args
        self.assertEqual(args[0], "PUT")
        self.assertEqual(args[1], "https://sandbox.zenodo.org/api/files/example/paper.pdf")
        self.assertIsNotNone(kwargs["data"])

    def test_publish_requires_explicit_confirmation(self):
        draft = Draft(124, "10.5072/zenodo.124",
                      "https://sandbox.zenodo.org/api/files/example",
                      "https://sandbox.zenodo.org/deposit/124")
        with self.assertRaises(ZenodoError):
            self.client.publish(draft)
        self.session.request.assert_not_called()
        self.session.request.return_value = response({
            "submitted": True, "doi": "10.5072/zenodo.124",
            "record_url": "https://sandbox.zenodo.org/records/124",
        }, status=202)
        doi, _ = self.client.publish(draft, confirmed=True)
        self.assertEqual(doi, "10.5072/zenodo.124")

    @patch.dict("os.environ", {}, clear=True)
    def test_missing_token_fails_closed(self):
        with self.assertRaises(ZenodoError):
            ZenodoSandboxClient()
