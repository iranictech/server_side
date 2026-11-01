import unittest
from unittest.mock import Mock

import requests

from reviewer_matching.identity import (
    normalize_orcid,
    extract_openalex_orcid,
)
from reviewer_matching.orcid_client import fetch_public_email


ORCID = "0000-0002-1825-0097"


class OrcidIdentityTests(unittest.TestCase):

    def test_normalize_orcid_variants(self):
        self.assertEqual(
            normalize_orcid(
                f" https://orcid.org/{ORCID}/ "
            ),
            ORCID,
        )
        self.assertEqual(normalize_orcid(ORCID), ORCID)

    def test_reject_invalid_orcid_and_url(self):
        self.assertEqual(
            normalize_orcid("https://example.org/private"),
            "",
        )
        self.assertEqual(
            normalize_orcid("../0000-0002-1825-0097"),
            "",
        )

    def test_extract_orcid_from_openalex_authorship(self):
        record = {
            "author": {
                "id": "https://openalex.org/A12345",
                "display_name": "Example",
                "orcid": f"https://orcid.org/{ORCID}",
            }
        }
        self.assertEqual(
            extract_openalex_orcid(record), ORCID
        )

    def test_missing_orcid_does_not_guess(self):
        self.assertEqual(
            extract_openalex_orcid({
                "author": {"display_name": "Example"}
            }),
            "",
        )

    def test_disabled_by_default(self):
        session = Mock()
        result = fetch_public_email(
            ORCID,
            access_token="fake-test-token",
            session=session,
        )
        self.assertEqual(result["status"], "disabled")
        session.get.assert_not_called()

    def test_missing_token_blocks_request(self):
        session = Mock()
        result = fetch_public_email(
            ORCID,
            enabled=True,
            access_token="",
            session=session,
        )
        self.assertEqual(result["status"], "missing_token")
        session.get.assert_not_called()

    def test_public_verified_email(self):
        session = Mock()
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "email": [
                {
                    "email": "researcher@example.org",
                    "verified": True,
                    "visibility": "public",
                    "primary": True,
                    "current": True,
                }
            ]
        }
        session.get.return_value = response

        result = fetch_public_email(
            ORCID,
            enabled=True,
            access_token="fake-test-token",
            session=session,
        )

        self.assertEqual(result["status"], "available")
        self.assertEqual(
            result["email"], "researcher@example.org"
        )

    def test_private_and_unverified_not_returned(self):
        session = Mock()
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "email": [
                {
                    "email": "private@example.org",
                    "verified": True,
                    "visibility": "private",
                },
                {
                    "email": "unverified@example.org",
                    "verified": False,
                    "visibility": "public",
                },
            ]
        }
        session.get.return_value = response

        result = fetch_public_email(
            ORCID,
            enabled=True,
            access_token="fake-test-token",
            session=session,
        )

        self.assertEqual(result["status"], "not_public")
        self.assertIsNone(result["email"])

    def test_network_failure_handled(self):
        session = Mock()
        session.get.side_effect = requests.Timeout()

        result = fetch_public_email(
            ORCID,
            enabled=True,
            access_token="fake-test-token",
            session=session,
        )

        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["email"])

    def test_invalid_payload_handled(self):
        session = Mock()
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"unexpected": []}
        session.get.return_value = response

        result = fetch_public_email(
            ORCID,
            enabled=True,
            access_token="fake-test-token",
            session=session,
        )

        self.assertEqual(result["status"], "unavailable")

    def test_fixed_api_url_and_auth_header(self):
        session = Mock()
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"email": []}
        session.get.return_value = response

        fetch_public_email(
            ORCID,
            enabled=True,
            access_token="fake-test-token",
            session=session,
        )

        args, kwargs = session.get.call_args

        self.assertEqual(
            args[0],
            f"https://pub.orcid.org/v3.0/{ORCID}/email",
        )
        self.assertEqual(
            kwargs["headers"]["Authorization"],
            "Bearer fake-test-token",
        )
        self.assertFalse(kwargs["allow_redirects"])
