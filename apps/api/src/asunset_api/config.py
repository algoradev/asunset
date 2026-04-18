from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    asunset_env: Literal["dev", "staging", "prod"] = "dev"

    app_db_url: str = Field(
        ...,
        description="Regular app connection URL — non-owner, subject to RLS.",
    )
    app_admin_db_url: str = Field(
        ...,
        description=(
            "Admin connection URL — schema owner, used for migrations and "
            "platform ops (bootstrap, reconcile). Bypasses RLS as table owner."
        ),
    )

    # Keycloak: two issuer URLs so the app can both (a) validate the `iss`
    # claim as the browser sees it and (b) fetch JWKS from the in-cluster
    # service DNS without going out through a public hostname.
    keycloak_issuer: str
    keycloak_internal_issuer: str
    keycloak_realm: str = "asunset"
    keycloak_api_client_id: str
    keycloak_api_client_secret: str

    @property
    def keycloak_internal_base(self) -> str:
        """Internal base URL (no /realms/... suffix) — used for the admin API."""
        marker = "/realms/"
        if marker in self.keycloak_internal_issuer:
            return self.keycloak_internal_issuer.split(marker, 1)[0]
        return self.keycloak_internal_issuer

    openfga_api_url: str
    openfga_store_name: str = "asunset"
    openfga_api_key: str

    api_cors_origins: str = "http://localhost:3000"
    api_log_level: str = "info"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.api_cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
