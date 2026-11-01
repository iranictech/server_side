import unittest
from types import SimpleNamespace
from unittest.mock import patch

from reviewer_matching.combined import build_combined_matches
from reviewer_matching.openalex import OpenAlexDiscoveryError


class CombinedTests(unittest.TestCase):

    def setUp(self):
        self.article = SimpleNamespace(pk=123)
        self.editor = SimpleNamespace(pk=50)

    @patch("reviewer_matching.combined.discover_external_researchers")
    @patch("reviewer_matching.combined.get_internal_matches")
    def test_both_sources(self, internal, external):
        internal.return_value = [{"account_id": 7}]
        external.return_value = [{"openalex_id": "A123"}]

        result = build_combined_matches(
            self.article,
            self.editor,
            public_topics=["Machine Learning"],
            allow_external=True,
        )

        self.assertEqual(result["counts"]["internal"], 1)
        self.assertEqual(result["counts"]["external"], 1)
        self.assertTrue(result["internal_priority"])
        self.assertFalse(result["automatic_invitation"])

    @patch("reviewer_matching.combined.discover_external_researchers")
    @patch("reviewer_matching.combined.get_internal_matches")
    def test_external_disabled_by_default(self, internal, external):
        internal.return_value = [{"account_id": 7}]

        result = build_combined_matches(
            self.article,
            self.editor,
            public_topics=["Artificial Intelligence"],
        )

        external.assert_not_called()
        self.assertEqual(result["external_status"], "disabled")
        self.assertEqual(result["counts"]["internal"], 1)

    @patch("reviewer_matching.combined.discover_external_researchers")
    @patch("reviewer_matching.combined.get_internal_matches")
    def test_external_failure_keeps_internal(self, internal, external):
        internal.return_value = [{"account_id": 7}]
        external.side_effect = OpenAlexDiscoveryError("Unavailable")

        result = build_combined_matches(
            self.article,
            self.editor,
            public_topics=["Statistics"],
            allow_external=True,
        )

        self.assertEqual(result["external_status"], "unavailable")
        self.assertEqual(result["counts"]["internal"], 1)
        self.assertEqual(result["counts"]["external"], 0)
