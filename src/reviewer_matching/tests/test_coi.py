"""Local-only coauthorship evidence regression tests."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from reviewer_matching.coi import (
    get_article_author_orcids,
    sampled_coauthorship_evidence,
)


class CoiEvidenceTests(unittest.TestCase):
    @patch("reviewer_matching.coi.FrozenAuthor")
    def test_collect_author_orcids_from_both_sources(self, frozen):
        frozen.objects.filter.return_value.values_list.return_value = [
            "https://orcid.org/0000-0001-2345-6789",
            None,
        ]
        accounts = Mock()
        accounts.values_list.return_value = [
            "0000-0002-1825-0097",
            "not-an-orcid",
        ]
        article = SimpleNamespace(author_accounts=accounts)

        result = get_article_author_orcids(article)

        self.assertEqual(result, {"0000-0001-2345-6789", "0000-0002-1825-0097"})
        frozen.objects.filter.assert_called_once_with(article=article)
        accounts.values_list.assert_called_once_with("orcid", flat=True)

    def test_only_valid_sampled_work_ids_are_evidence(self):
        result = sampled_coauthorship_evidence(
            {
                "https://orcid.org/0000-0001-2345-6789": [
                    "W55",
                    "W55",
                    "https://invalid.example/W77",
                    None,
                    "W44",
                ],
                "0000-0002-1825-0097": ["W99"],
            },
            {"0000-0001-2345-6789"},
        )
        self.assertEqual(result, ["W44", "W55"])

    def test_missing_evidence_is_never_coi_clearance(self):
        self.assertEqual(
            sampled_coauthorship_evidence(None, {"0000-0001-2345-6789"}),
            [],
        )
        self.assertEqual(
            sampled_coauthorship_evidence({"0000-0001-2345-6789": ["W1"]}, set()),
            [],
        )
