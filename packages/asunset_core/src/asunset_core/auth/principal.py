from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID


@dataclass(frozen=True, slots=True)
class Principal:
    """The authenticated caller, derived from a validated Keycloak JWT.

    Held in request.state after auth, passed into business logic so routes
    never touch raw tokens. Roles here are realm roles only (platform_admin,
    platform_support) — per-org / per-team / per-resource authorization is
    answered by the Authorizer port, never by inspecting this object.
    """

    user_id: UUID
    email: str
    display_name: str
    realm_roles: frozenset[str] = field(default_factory=frozenset)
    # Keycloak session id — same for every request within one SSO
    # session. For agent sessions this is the MINTED session's own id,
    # which is what lets audit distinguish agent sessions with no schema
    # change. Used by audit to flag credential misuse ("same user,
    # simultaneous sessions from different IPs").
    session_id: str | None = None
    # Set only for agent session tokens (typ=asunset-session): the acting
    # agent from the `act` claim. sub/user_id is ALWAYS the human (D1).
    agent_id: str | None = None
    # "login" (Keycloak-issued) or "session" (asunset-minted, D4).
    token_type: str = "login"

    @property
    def is_agent_session(self) -> bool:
        return self.token_type == "session"

    @property
    def is_platform_admin(self) -> bool:
        return "platform_admin" in self.realm_roles

    @property
    def is_platform_support(self) -> bool:
        return "platform_support" in self.realm_roles

    def fga_user(self) -> str:
        """OpenFGA object identifier for this principal."""
        return f"user:{self.user_id}"
