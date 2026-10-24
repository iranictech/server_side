
from utils import models as utils_models


PLUGIN_NAME = "abstract_indexing"
DISPLAY_NAME = "Abstract Indexing"
DESCRIPTION = (
    "Homepage element for managing abstracting and indexing services for journals."
)
AUTHOR = "Custom Plugin"
VERSION = "1.0"
JANEWAY_VERSION = "1.8.0"


def install():
    """
    Register the Abstract Indexing plugin.

    Do not create or update HomepageElement records for journals.
    Homepage elements must be registered separately for each journal.
    """
    plugin, created = utils_models.Plugin.objects.get_or_create(
        name=PLUGIN_NAME,
        defaults={
            "version": VERSION,
            "enabled": True,
        },
    )

    plugin.display_name = DISPLAY_NAME
    plugin.version = VERSION
    plugin.homepage_element = True

    # Preserve the enabled state of existing installations.
    if created:
        plugin.enabled = True

    plugin.save()

    return plugin


def hook_registry():
    """
    Register plugin hooks without modifying the database.
    """
    return {
        "yield_homepage_element_context": {
            "module": "plugins.abstract_indexing.hooks",
            "function": "yield_homepage_element_context",
            "name": DISPLAY_NAME,
        }
    }


def register_for_events():
    pass
