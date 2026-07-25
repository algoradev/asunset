"""asunset_api process settings.

Extends `asunset_core.config.CoreSettings` with the Notes-demo-specific
fields. Consumer products do the same pattern in their own repos.
"""

from functools import lru_cache
from typing import Literal

from asunset_core.config import CoreSettings


class Settings(CoreSettings):
    asunset_env: Literal["dev", "staging", "prod"] = "dev"
    # The demo ships a manifest (audit.view); consumers set their own
    # path or empty to disable.
    features_manifest: str = "features.yaml"
    api_cors_origins: str = "http://localhost:3000"
    api_log_level: str = "info"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.api_cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
