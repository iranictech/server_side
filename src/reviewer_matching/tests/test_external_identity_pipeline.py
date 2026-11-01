import unittest
from types import SimpleNamespace
from unittest.mock import patch

from reviewer_matching.combined import build_combined_matches


ORCID = "0000-0002-1825-0097"


class ExternalIdentityPipelineTests(unittest.TestCase):

    def setUp(self):
        self.article = SimpleNamespace(pk=123)
        self.editor = SimpleNamespace(pk=50)

    def candidate(self, orcid=ORCID, status="available"):
        return {
            "openalex_id": "A123",
            "name": "Example Researcher",
            "orcid": orcid,
            "orcid_status": status,
        }

    @patch(
        "reviewer_matching.combined.fetch_public_email"
    )
    @patch(
        "reviewer_matching.combined.resolve_janeway_orcid",
        return_value="new_external",
    )
    @patch(
        "reviewer_matching.combined.discover_external_researchers"
    )
    @patch(
        "reviewer_matching.combined.get_internal_matches",
        return_value=[],
    )
    def test_default_does_not_fetch_email(
        self, internal, discovery, resolver, email
    ):
        discovery.return_value = [self.candidate()]

        result = build_combined_matches(
            self.article,
            self.editor,
            public_topics=["Machine Learning"],
            allow_external=True,
        )

        self.assertEqual(
            result["results"]["external"][0]["email_status"],
            "disabled",
        )
        email.assert_not_called()

    @patch(
        "reviewer_matching.combined.fetch_public_email",
        return_value={
            "email": "example@example.org",
            "status": "available",
            "source": "orcid_public_api",
        },
    )
    @patch(
        "reviewer_matching.combined.resolve_janeway_orcid",
        return_value="new_external",
    )
    @patch(
        "reviewer_matching.combined.discover_external_researchers"
    )
    @patch(
        "reviewer_matching.combined.get_internal_matches",
        return_value=[],
    )
    def test_explicit_email_lookup(
        self, internal, discovery, resolver, email
    ):
        discovery.return_value = [self.candidate()]

        result = build_combined_matches(
            self.article,
            self.editor,
            public_topics=["Machine Learning"],
            allow_external=True,
            allow_orcid_email=True,
        )

        candidate = result["results"]["external"][0]

        self.assertEqual(
            candidate["email"],
            "example@example.org",
        )
        self.assertFalse(candidate["invitation_ready"])
        email.assert_called_once_with(
            ORCID,
            enabled=True,
        )

    @patch(
        "reviewer_matching.combined.fetch_public_email"
    )
    @patch(
        "reviewer_matching.combined.resolve_janeway_orcid"
    )
    @patch(
        "reviewer_matching.combined.discover_external_researchers"
    )
    @patch(
        "reviewer_matching.combined.get_internal_matches",
        return_value=[],
    )
    def test_ambiguous_orcid_is_not_queried(
        self, internal, discovery, resolver, email
    ):
        discovery.return_value = [
            self.candidate(None, "ambiguous")
        ]

        result = build_combined_matches(
            self.article,
            self.editor,
            public_topics=["Statistics"],
            allow_external=True,
            allow_orcid_email=True,
        )

        candidate = result["results"]["external"][0]

        self.assertEqual(
            candidate["identity_status"],
            "ambiguous_orcid",
        )
        self.assertIsNone(candidate["email"])
        resolver.assert_not_called()
        email.assert_not_called()

    @patch(
        "reviewer_matching.combined.fetch_public_email"
    )
    @patch(
        "reviewer_matching.combined.resolve_janeway_orcid",
        return_value="new_external",
    )
    @patch(
        "reviewer_matching.combined.discover_external_researchers"
    )
    @patch(
        "reviewer_matching.combined.get_internal_matches",
        return_value=[],
    )
    def test_email_lookup_has_request_limit(
        self, internal, discovery, resolver, email
    ):
        discovery.return_value = [
            {
                **self.candidate(),
                "openalex_id": f"A{i}",
            }
            for i in range(5)
        ]

        email.return_value = {
            "email": None,
            "status": "not_public",
            "source": "orcid_public_api",
        }

        result = build_combined_matches(
            self.article,
            self.editor,
            public_topics=["Statistics"],
            allow_external=True,
            allow_orcid_email=True,
        )

        self.assertEqual(email.call_count, 3)
        self.assertEqual(
            result["results"]["external"][4]["email_status"],
            "not_checked_limit",
        )
