"""
Independent Production authorization.
Default deny.
"""

from django.conf import settings
from identifiers.zenodo_journal_policy import zenodo_enabled


def is_production_article_allowed(article):
    return bool(
        article.pk
        and article.pk != 40
        and article.journal_id
        and zenodo_enabled(article.journal)
    )


def can_operate_zenodo_production(request, article):
    allowed_users = getattr(
        settings,
        "ZENODO_PRODUCTION_ALLOWED_USERS",
        (),
    )

    return bool(
        getattr(
            settings,
            "ZENODO_PRODUCTION_WRITE_ENABLED",
            False,
        )
        and request.user.is_authenticated
        and request.user.is_active
        and request.user.is_superuser
        and request.user.pk in allowed_users
        and request.journal
        and article.journal_id == request.journal.pk
        and is_production_article_allowed(article)
    )
