from django.apps import AppConfig


class AbstractIndexingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "plugins.abstract_indexing"