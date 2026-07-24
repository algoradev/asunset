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

    # App-side email notifier. `log` is the safe default; `resend`
    # switches to real delivery and requires `resend_api_key`. Keep
    # `log` as the default so a fresh checkout / CI run never sends
    # mail accidentally.
    notifier_backend: str = Field(
        default="log",
        description="`log` (dev, no network) or `resend` (HTTP API).",
    )
    resend_api_key: str = ""
    notifier_default_sender: str = Field(
        default="noreply@asunset.local",
        description="`From:` header on every app-side email. Operator overrides per deploy.",
    )
    notifier_default_locale: str = "en"
    notifier_template_dir: str = Field(
        default="",
        description=(
            "Filesystem path to a directory of consumer-owned email templates. "
            "Searched before the bundled asunset defaults, so a consumer can "
            "override a single template without copying the whole set. Leave "
            "empty to use only the bundled templates."
        ),
    )

    # How org invites bootstrap a new user's credential.
    #
    #   magic_link    Keycloak emails the recipient a one-time link that
    #                 lands them on the set-password screen, then
    #                 redirects to the app. Requires KC_SMTP_HOST and a
    #                 reachable SMTP gateway.
    #
    #   temp_password Backend generates a strong temp password, sets it
    #                 on the new KC user with `temporary=true` (so KC
    #                 forces UPDATE_PASSWORD on first login), and
    #                 returns it in the API response. Admin conveys it
    #                 out-of-band. Use this when outbound SMTP is
    #                 blocked (Linode, etc.).
    #
    #   auto          Try magic_link first; if Keycloak's
    #                 executeActionsEmail errors (commonly: SMTP not
    #                 configured / gateway unreachable), fall back to
    #                 temp_password automatically. Trades a small
    #                 latency on failure for resilience.
    invite_delivery: str = Field(
        default="magic_link",
        description="One of `magic_link`, `temp_password`, `auto`.",
    )

    # Extra audience values stamped into web tokens, one per additional
    # resource server (identity contract D6). Mirrors the value given to
    # keycloak-init; the API uses it to validate mint requests' audience
    # subsets.
    keycloak_extra_audiences: str = ""

    # --- agent session tokens (D4 mint; docs/session-token-mint-spec.md) --
    # base64-encoded RSA private key PEM. Empty = ephemeral per-process
    # key (dev only — sessions die on restart; the signer logs a warning).
    session_token_private_key_b64: str = ""
    # Issuer string for session tokens. Never fetched as a URL —
    # validators match it exactly and select the session JWKS source.
    session_token_issuer: str = ""
    session_token_max_ttl_seconds: int = 3600

    @property
    def resolved_session_token_issuer(self) -> str:
        return self.session_token_issuer or f"urn:asunset:sessions:{self.keycloak_realm}"

    @property
    def allowed_audiences(self) -> list[str]:
        extras = [a.strip() for a in self.keycloak_extra_audiences.split(",") if a.strip()]
        return [self.keycloak_api_client_id, *extras]

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
