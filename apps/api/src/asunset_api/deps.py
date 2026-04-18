"""FastAPI dependency providers.

Collected here so routers stay free of direct imports of DB sessions,
the Authorizer port, or token validation internals. This keeps routes
swappable and test-friendly — fake a dependency, swap the impl.

Concrete providers are filled in by the DB, auth, and audit tasks.
"""

from asunset_api.config import Settings, get_settings  # re-exported for convenience

__all__ = ["Settings", "get_settings"]
