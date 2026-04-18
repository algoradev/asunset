"""Platform-level settings shared by every asunset-based product.

Consumer products subclass `CoreSettings` in their own Settings class
to add app-specific fields. Each subclass gets its own lru_cache'd
getter — reading env vars twice (once for Core, once for the subclass)
is harmless and keeps the two processes loosely coupled.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class CoreSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # DB URLs: the split owner/app-user pattern is part of asunset's
    # RLS story; products connect as the app user for their request
    # handling and use the admin connection only for platform ops.
    app_db_url: str = Field(
        ..., description="Regular app connection URL — non-owner, subject to RLS."
    )
    app_admin_db_url: str = Field(
        ...,
        description=(
            "Admin connection URL — schema owner, used for migrations and "
            "platform ops (bootstrap, reconcile). Bypasses RLS as table owner."
        ),
    )

    # Keycloak split-issuer pattern: public is what browsers see (iss
    # claim target), internal is what this process uses to fetch JWKS.
    keycloak_issuer: str
    keycloak_internal_issuer: str
    keycloak_realm: str = "asunset"
    keycloak_api_client_id: str
    keycloak_api_client_secret: str

    # OpenFGA with preshared-key auth.
    openfga_api_url: str
    openfga_store_name: str = "asunset"
    openfga_api_key: str

    @property
    def keycloak_internal_base(self) -> str:
        """Internal base URL (no /realms/... suffix) — used for the admin API."""
        marker = "/realms/"
        if marker in self.keycloak_internal_issuer:
            return self.keycloak_internal_issuer.split(marker, 1)[0]
        return self.keycloak_internal_issuer


@lru_cache
def get_core_settings() -> CoreSettings:
    return CoreSettings()  # type: ignore[call-arg]
