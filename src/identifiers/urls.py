__copyright__ = "Copyright 2017 Birkbeck, University of London"
__author__ = "Martin Paul Eve & Andy Byers"
__license__ = "AGPL v3"
__maintainer__ = "Birkbeck Centre for Technology and Publishing"
from django.urls import re_path

from identifiers import views
from identifiers import zenodo_ui

from identifiers import zenodo_production_ui

urlpatterns = [
    re_path(
        r"^(?P<article_id>\d+)/zenodo/production/"
        r"(?P<action>prepare|create|upload|check|reconcile|publish|reconcile_publish)/$",
        zenodo_production_ui.zenodo_production_action,
        name="zenodo_production_action",
    ),

    re_path(
        r"^(?P<article_id>\d+)/zenodo/"
        r"(?P<action>prepare|create|upload|check|reconcile)/$",
        zenodo_ui.zenodo_action,
        name="zenodo_article_action",
    ),

    re_path(r"^pingback$", views.pingback, name="crossref_pingback"),
    re_path(
        r"^(?P<article_id>\d+)/$", views.article_identifiers, name="article_identifiers"
    ),
    re_path(
        r"^(?P<article_id>\d+)/$", views.article_identifiers, name="edit_identifiers"
    ),
    re_path(
        r"^(?P<article_id>\d+)/new/$",
        views.manage_identifier,
        name="add_new_identifier",
    ),
    re_path(
        r"^(?P<article_id>\d+)/edit/(?P<identifier_id>\d+)/$",
        views.manage_identifier,
        name="edit_identifier",
    ),
    re_path(
        r"^(?P<article_id>\d+)/delete/(?P<identifier_id>\d+)/$",
        views.delete_identifier,
        name="delete_identifier",
    ),
    re_path(
        r"^(?P<article_id>\d+)/issue/(?P<identifier_id>\d+)/$",
        views.issue_doi,
        name="issue_doi",
    ),
    re_path(
        r"^(?P<article_id>\d+)/show/(?P<identifier_id>\d+)/$",
        views.show_doi,
        name="show_doi",
    ),
    re_path(
        r"^(?P<article_id>\d+)/poll/(?P<identifier_id>\d+)/$",
        views.poll_doi,
        name="poll_doi",
    ),
    re_path(
        r"^(?P<article_id>\d+)/poll/output/(?P<identifier_id>\d+)/$",
        views.poll_doi_output,
        name="poll_doi_output",
    ),
    # DOI Manager
    re_path(
        r"^doi_manager/$",
        views.IdentifierManager.as_view(),
        name="journal_identifier_manager",
    ),
]
