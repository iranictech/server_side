import unittest

from reviewer_matching.ranking import rank_internal


def candidate(pk, matches, load):
    return {
        "account_id": pk,
        "matched_keywords": matches,
        "active_reviews": load,
    }


class RankingTests(unittest.TestCase):
    def test_expertise_first(self):
        rows = [
            candidate(1, [], 0),
            candidate(2, ["AI"], 3),
        ]
        result = rank_internal(rows)
        self.assertEqual(result[0]["account_id"], 2)

    def test_lower_workload_breaks_ties(self):
        rows = [
            candidate(1, ["AI"], 4),
            candidate(2, ["AI"], 1),
        ]
        result = rank_internal(rows)
        self.assertEqual(result[0]["account_id"], 2)

    def test_unknown_workload_ranks_after_known(self):
        rows = [
            candidate(1, [], None),
            candidate(2, [], 2),
        ]
        result = rank_internal(rows)
        self.assertEqual(result[0]["account_id"], 2)


if __name__ == "__main__":
    unittest.main()
