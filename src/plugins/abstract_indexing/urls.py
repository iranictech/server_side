from django.urls import re_path

from . import views


urlpatterns = [
    re_path(
        r"^$",
        views.abstract_indexing_config,
        name="abstract_indexing_config",
    ),
    re_path(
        r"^add/$",
        views.abstract_indexing_add,
        name="abstract_indexing_add",
    ),
    re_path(
        r"^register-homepage/$",
        views.abstract_indexing_register_homepage,
        name="abstract_indexing_register_homepage",
    ),
    re_path(
        r"^(?P<pk>\d+)/edit/$",
        views.abstract_indexing_edit,
        name="abstract_indexing_edit",
    ),
    re_path(
        r"^(?P<pk>\d+)/delete/$",
        views.abstract_indexing_delete,
        name="abstract_indexing_delete",
    ),
]