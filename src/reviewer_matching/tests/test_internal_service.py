import unittest
from types import SimpleNamespace
from unittest.mock import patch

from reviewer_matching.services import get_internal_matches


class FakeReviewer:
    def __init__(self, pk, email="", orcid="", interests=(), load=0, is_active=True):
        self.pk = pk
        self.is_active = is_active
        self.email = email
        self.orcid = orcid
        self.active_reviews_count = load
        self.interest = SimpleNamespace(
            all=lambda: [SimpleNamespace(name=name) for name in interests]
        )

    def full_name(self):
        return f"Reviewer {self.pk}"


class FakeQuerySet:
    def __init__(self, items):
        self.items = list(items)

    def exclude(self, **kwargs):
        assert len(kwargs) == 1
        key, values = next(iter(kwargs.items()))

        assert key.endswith("__in"), key
        field = key[:-4]
        excluded = set(values)

        return FakeQuerySet(
            [item for item in self.items if getattr(item, field) not in excluded]
        )

    def filter(self, **kwargs):
        assert kwargs == {"is_active": True}
        return FakeQuerySet([item for item in self.items if item.is_active])

    def distinct(self):
        by_pk = {}
        for item in self.items:
            by_pk.setdefault(item.pk, item)
        return FakeQuerySet(by_pk.values())

    def __iter__(self):
        return iter(self.items)


def make_article(words=(), author_ids=()):
    return SimpleNamespace(
        keywords=SimpleNamespace(
            all=lambda: [SimpleNamespace(word=word) for word in words]
        ),
        author_accounts=SimpleNamespace(
            values_list=lambda *args, **kwargs: list(author_ids)
        ),
    )


def execute_match(article, reviewers, frozen_authors=(), limit=20):
    frozen_result = SimpleNamespace(values=lambda *args: list(frozen_authors))

    with (
        patch(
            "reviewer_matching.services.get_reviewer_candidates",
            return_value=FakeQuerySet(reviewers),
        ),
        patch(
            "reviewer_matching.services.FrozenAuthor.objects.filter",
            return_value=frozen_result,
        ),
    ):
        return get_internal_matches(
            article,
            editor=SimpleNamespace(pk=999),
            limit=limit,
        )


class InternalReviewerServiceTests(unittest.TestCase):
    def test_excludes_article_author_account(self):
        article = make_article(
            words=["Artificial Intelligence"],
            author_ids=[1],
        )
        reviewers = [
            FakeReviewer(1, interests=["Artificial Intelligence"]),
            FakeReviewer(2, interests=["Artificial Intelligence"]),
        ]

        result = execute_match(article, reviewers)

        self.assertEqual(
            [item["account_id"] for item in result],
            [2],
        )

    def test_excludes_matching_author_email_and_orcid(self):
        article = make_article(words=["AI"])
        frozen = [
            {
                "author_id": None,
                "frozen_email": "author@example.org",
                "frozen_orcid": "0000-0001-1234-5678",
            }
        ]
        reviewers = [
            FakeReviewer(1, email="author@example.org"),
            FakeReviewer(2, orcid="0000-0001-1234-5678"),
            FakeReviewer(3, email="other@example.org"),
        ]

        result = execute_match(article, reviewers, frozen)

        self.assertEqual(
            [item["account_id"] for item in result],
            [3],
        )

    def test_excludes_author_when_email_orcid_formats_differ(self):
        article = make_article(words=["AI"])
        frozen = [
            {
                "author_id": None,
                "frozen_email": "Author@Example.Org ",
                "frozen_orcid": "https://orcid.org/0000-0002-1825-0097/",
            }
        ]
        reviewers = [
            FakeReviewer(1, email="author@example.org"),
            FakeReviewer(2, orcid="0000-0002-1825-0097"),
            FakeReviewer(3, orcid="https://orcid.org/0000-0002-1825-0097"),
            FakeReviewer(4, email="unrelated@example.org"),
        ]

        result = execute_match(article, reviewers, frozen)
        self.assertEqual([item["account_id"] for item in result], [4])

    def test_inactive_accounts_are_never_suggested(self):
        article = make_article(words=["Artificial Intelligence"])
        reviewers = [
            FakeReviewer(1, interests=["Artificial Intelligence"], is_active=False),
            FakeReviewer(2, interests=["Artificial Intelligence"]),
        ]

        result = execute_match(article, reviewers)

        self.assertEqual([item["account_id"] for item in result], [2])

    def test_keyword_matching_is_case_insensitive(self):
        article = make_article(words=["Machine Learning"])
        reviewers = [
            FakeReviewer(
                7,
                interests=["machine learning", "Statistics"],
            )
        ]

        result = execute_match(article, reviewers)

        self.assertEqual(
            result[0]["matched_keywords"],
            ["machine learning"],
        )
        self.assertEqual(
            result[0]["expertise_evidence"],
            "exact_keyword_overlap",
        )

    def test_missing_interests_are_reported(self):
        article = make_article(words=["AI"])
        reviewers = [FakeReviewer(8, interests=[])]

        result = execute_match(article, reviewers)

        self.assertEqual(
            result[0]["expertise_evidence"],
            "insufficient_evidence",
        )
        self.assertFalse(result[0]["invitation_ready"])

    def test_limit_is_respected(self):
        article = make_article(words=["AI"])
        reviewers = [
            FakeReviewer(1),
            FakeReviewer(2),
            FakeReviewer(3),
        ]

        result = execute_match(article, reviewers, limit=2)

        self.assertEqual(len(result), 2)


if __name__ == "__main__":
    unittest.main()
