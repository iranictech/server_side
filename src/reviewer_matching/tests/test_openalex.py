import unittest
from unittest.mock import Mock

import requests

from reviewer_matching.openalex import (
    OpenAlexDiscoveryError,
    discover_external_researchers,
    validate_public_topics,
)


def work(work_id, authors):
    return {
        "id": f"https://openalex.org/W{work_id}",
        "title": "Public research work",
        "publication_year": 2025,
        "authorships": [
            {
                "author": {
                    "id": f"https://openalex.org/A{author_id}",
                    "display_name": name,
                }
            }
            for author_id, name in authors
        ],
    }


def response_for(works):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"results": works}
    return response


class OpenAlexTests(unittest.TestCase):
    def test_validate_public_topics(self):
        self.assertEqual(
            validate_public_topics(["Machine Learning", "machine learning"]),
            ["Machine Learning"],
        )

    def test_reject_non_public_lengthy_input(self):
        with self.assertRaises(ValueError):
            validate_public_topics(["A" * 200])

    def test_discover_and_deduplicate_authors(self):
        session = Mock()
        session.get.return_value = response_for(
            [
                work(101, [(1, "Researcher One")]),
                work(
                    102,
                    [
                        (1, "Researcher One"),
                        (2, "Researcher Two"),
                    ],
                ),
            ]
        )

        result = discover_external_researchers(
            ["Fuzzy Logic"],
            session=session,
        )

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["openalex_id"], "A1")
        self.assertEqual(result[0]["matching_works_count"], 2)
        self.assertFalse(result[0]["invitation_ready"])
        self.assertIsNone(result[0]["semantic_score"])

        args, kwargs = session.get.call_args
        self.assertEqual(
            kwargs["params"]["search"],
            "Fuzzy Logic",
        )
        self.assertEqual(
            args[0],
            "https://api.openalex.org/works",
        )

    def test_api_key_uses_header_not_url(self):
        session = Mock()
        session.get.return_value = response_for([])

        discover_external_researchers(
            ["Artificial Intelligence"],
            api_key="test-secret",
            session=session,
        )

        kwargs = session.get.call_args.kwargs

        self.assertEqual(
            kwargs["headers"]["Authorization"],
            "Bearer test-secret",
        )
        self.assertNotIn("api_key", kwargs["params"])

    def test_network_errors_are_handled(self):
        session = Mock()
        session.get.side_effect = requests.Timeout()

        with self.assertRaises(OpenAlexDiscoveryError):
            discover_external_researchers(
                ["Machine Learning"],
                session=session,
            )

    def test_reject_malformed_author_ids(self):
        session = Mock()
        session.get.return_value = response_for(
            [
                {
                    "id": "https://openalex.org/W100",
                    "authorships": [
                        {
                            "author": {
                                "id": "https://invalid.example/A100",
                                "display_name": "Unknown",
                            }
                        }
                    ],
                }
            ]
        )

        result = discover_external_researchers(
            ["Data Science"],
            session=session,
        )

        self.assertEqual(result, [])

    def test_extract_primary_orcid_from_work(self):
        record = work(300, [(3, "Researcher Three")])
        record["authorships"][0]["author"]["orcid"] = (
            "https://orcid.org/0000-0002-1825-0097"
        )

        session = Mock()
        session.get.return_value = response_for([record])

        result = discover_external_researchers(
            ["Machine Learning"],
            session=session,
        )

        self.assertEqual(
            result[0]["orcid"],
            "0000-0002-1825-0097",
        )
        self.assertEqual(
            result[0]["orcid_status"],
            "available",
        )

    def test_conflicting_orcids_are_ambiguous(self):
        first = work(301, [(3, "Researcher Three")])
        second = work(302, [(3, "Researcher Three")])

        first["authorships"][0]["author"]["orcid"] = (
            "https://orcid.org/0000-0002-1825-0097"
        )
        second["authorships"][0]["author"]["orcid"] = (
            "https://orcid.org/0000-0001-2345-6789"
        )

        session = Mock()
        session.get.return_value = response_for([first, second])

        result = discover_external_researchers(
            ["Machine Learning"],
            session=session,
        )

        self.assertIsNone(result[0]["orcid"])
        self.assertEqual(
            result[0]["orcid_status"],
            "ambiguous",
        )

    def test_raw_orcid_is_not_trusted_as_primary(self):
        record = work(303, [(3, "Researcher Three")])
        record["authorships"][0]["raw_orcid"] = "0000-0002-1825-0097"

        session = Mock()
        session.get.return_value = response_for([record])

        result = discover_external_researchers(
            ["Machine Learning"],
            session=session,
        )

        self.assertIsNone(result[0]["orcid"])
        self.assertEqual(
            result[0]["orcid_status"],
            "missing",
        )

    def test_latest_year_only_from_sampled_matching_works(self):
        older = work(401, [(3, "Researcher Three")])
        newer = work(402, [(3, "Researcher Three")])
        older["publication_year"] = 2019
        newer["publication_year"] = 2025

        session = Mock()
        session.get.return_value = response_for([older, newer])

        result = discover_external_researchers(
            ["Machine Learning"],
            session=session,
        )

        self.assertEqual(result[0]["latest_sampled_publication_year"], 2025)
        self.assertEqual(result[0]["activity_status"], "not_assessed")
        self.assertFalse(result[0]["invitation_ready"])

    def test_missing_or_invalid_publication_year_is_not_activity_evidence(self):
        values = [None, "", "2025", True, 0, 1499, 9999]
        records = []
        for index, year in enumerate(values):
            record = work(index + 501, [(3, "Researcher Three")])
            record["publication_year"] = year
            records.append(record)

        session = Mock()
        session.get.return_value = response_for(records)

        result = discover_external_researchers(
            ["Statistics"],
            session=session,
        )

        self.assertEqual(result[0]["latest_sampled_publication_year"], None)
        self.assertEqual(result[0]["activity_status"], "not_assessed")
        self.assertEqual(result[0]["matching_works_count"], len(values))

    def test_sampled_year_does_not_imply_latest_overall_publication(self):
        old_sample = work(601, [(3, "Researcher Three")])
        old_sample["publication_year"] = 2010

        session = Mock()
        session.get.return_value = response_for([old_sample])

        result = discover_external_researchers(
            ["Statistics"],
            session=session,
        )

        self.assertEqual(result[0]["latest_sampled_publication_year"], 2010)
        self.assertEqual(result[0]["activity_status"], "not_assessed")

    def test_public_coauthor_orcid_evidence_uses_same_sampled_work(self):
        record = work(701, [(10, "Candidate"), (11, "Manuscript Author")])
        record["authorships"][0]["author"]["orcid"] = "0000-0002-1825-0097"
        record["authorships"][1]["author"]["orcid"] = (
            "https://orcid.org/0000-0001-2345-6789"
        )
        session = Mock()
        session.get.return_value = response_for([record])

        result = discover_external_researchers(
            ["Machine Learning"],
            session=session,
        )

        candidate = next(row for row in result if row["openalex_id"] == "A10")
        self.assertEqual(
            candidate["_coauthor_orcid_work_ids"],
            {"0000-0001-2345-6789": ["W701"]},
        )
        self.assertFalse(candidate["invitation_ready"])
        self.assertEqual(session.get.call_count, 1)

    def test_unverified_raw_orcid_cannot_create_coauthor_evidence(self):
        record = work(702, [(10, "Candidate"), (11, "Author")])
        record["authorships"][1]["raw_orcid"] = "0000-0001-2345-6789"
        session = Mock()
        session.get.return_value = response_for([record])

        result = discover_external_researchers(
            ["Statistics"],
            session=session,
        )

        candidate = next(row for row in result if row["openalex_id"] == "A10")
        self.assertEqual(candidate["_coauthor_orcid_work_ids"], {})


if __name__ == "__main__":
    unittest.main()
