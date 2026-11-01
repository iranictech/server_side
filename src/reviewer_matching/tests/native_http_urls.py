"""Native HTTP tests using the complete Janeway URLConf.
No direct reviewer-matching plugin registration.
"""

from importlib import import_module

urlpatterns = list(import_module('core.urls').urlpatterns)
