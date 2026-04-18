"""Product settings — extends asunset's CoreSettings.

Every consumer Settings class extends CoreSettings so platform env vars
(DB URLs, Keycloak, OpenFGA) resolve the same way in every product.
Add your product-specific fields here.
"""

from functools import lru_cache
from typing import Literal

from asunset_core.config import CoreSettings


class Settings(CoreSettings):
    product_env: Literal["dev", "staging", "prod"] = "dev"
    api_cors_origins: str = "http://localhost:3000"
    api_log_level: str = "info"

    # Add your product-specific fields here — feature flags, third-party
    # API keys, retention overrides, etc.

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.api_cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
