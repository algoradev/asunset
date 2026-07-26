"""Scope resolvers — declared reach for capabilities (spec §11).

STABILITY CONTRACT: this registration seam is contract-§5-class frozen
(review #2, kestrel's subtree-pull warning). Consumers register
resolvers at startup by stable name + resource type; a subtree pull
will not change these signatures without a major, announced break.

THE NARROW-ONLY RULE, enforced by construction rather than convention:
a resolver receives (principal, reader) where `reader` is a READ-ONLY
facade over the Authorizer — check / list_objects / read_tuples only.
It can therefore FILTER what the Authorizer admits but never widen it
(worst case under a drifted implementation: the caller sees everything
the Authorizer already permits — never something illegal), and it has
no database or lifecycle access, so SCOPES ARE LIFECYCLE-BLIND is a
property of the signature, not a doctrine to police. "Formal export
touches only approved artifacts" belongs in the gate's consumption
list, and a resolver structurally cannot express it.

The residual gap — "did the handler actually call the resolver" — is
test-enforced (generated skeletons, spec §11); the preferred pattern is
resolver-as-sole-data-door: the handler's object set comes ONLY from
`resolve_scope`.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Protocol

from asunset_core.auth.principal import Principal


class AuthorizerReader:
    """Read-only facade handed to resolvers. Deliberately owns no write
    or admin surface — there is nothing to misuse."""

    def __init__(self, authorizer: Any) -> None:
        self._a = authorizer

    async def check(self, user: str, relation: str, object: str) -> bool:
        return await self._a.check(user, relation, object)

    async def list_objects(self, user: str, relation: str, object_type: str) -> list[str]:
        return await self._a.list_objects(user, relation, object_type)

    async def list_users(self, object: str, relation: str, user_type: str = "user") -> list[str]:
        return await self._a.list_users(object, relation, user_type)

    async def read_tuples(self, **kwargs: Any) -> Any:
        return await self._a.read_tuples(**kwargs)


ScopeResolver = Callable[[Principal, AuthorizerReader], Awaitable[list[str]]]
"""async (principal, reader) -> object ids of the pair's resource_type.
Return ONLY ids derived from reader queries — that's the whole job."""


class ResolverNotRegistered(RuntimeError):
    """A manifest-declared (resource_type, resolver) has no registered
    implementation — fail loud at startup, same posture as gate-key
    validation (a missing resolver would be a silent empty scope)."""


class ScopeResolverRegistry:
    def __init__(self) -> None:
        self._resolvers: dict[tuple[str, str], ScopeResolver] = {}

    def register(self, resource_type: str, name: str, fn: ScopeResolver) -> None:
        key = (resource_type, name)
        if key in self._resolvers:
            raise ValueError(
                f"scope resolver {name!r} for {resource_type!r} already registered — "
                f"names are stable identifiers; re-registration hides drift"
            )
        self._resolvers[key] = fn

    def get(self, resource_type: str, name: str) -> ScopeResolver:
        try:
            return self._resolvers[(resource_type, name)]
        except KeyError:
            raise ResolverNotRegistered(
                f"no scope resolver {name!r} registered for resource type "
                f"{resource_type!r} — register it at startup (authz/scopes.py-style)"
            ) from None

    def validate_manifest(self, declared: set[tuple[str, str]]) -> None:
        """Every manifest-declared (resource_type, resolver) must exist.
        Called at startup next to gate-key validation; raises on the
        first missing one with the full missing set named."""
        missing = sorted(d for d in declared if d not in self._resolvers)
        if missing:
            raise ResolverNotRegistered(
                f"manifest declares scope resolvers that are not registered: {missing}"
            )

    def known(self) -> set[tuple[str, str]]:
        return set(self._resolvers)


# Process-wide registry — consumers call scope_registry().register(...)
# at startup; the platform validates the manifest against it.
_registry: ScopeResolverRegistry | None = None


def scope_registry() -> ScopeResolverRegistry:
    global _registry
    if _registry is None:
        _registry = ScopeResolverRegistry()
    return _registry


def reset_scope_registry() -> None:
    """Test hook."""
    global _registry
    _registry = None


async def resolve_scope(
    manifest: Any,  # FeatureManifest — Any avoids a circular import
    key: str,
    resource_type: str,
    principal: Principal,
    authorizer: Any,
) -> list[str]:
    """Resolve a capability's declared scope for one resource type —
    the sole-data-door entry point handlers consume. Raises if the
    capability declares no scope for the type (an undeclared reach is
    a design gap, not an empty list)."""
    f = next((x for x in manifest.features if x.key == key), None)
    if f is None:
        raise ResolverNotRegistered(f"unknown feature {key!r}")
    pair = next((sp for sp in f.scopes if sp.resource_type == resource_type), None)
    if pair is None:
        raise ResolverNotRegistered(
            f"feature {key!r} declares no scope for resource type {resource_type!r}"
        )
    fn = scope_registry().get(resource_type, pair.resolver)
    return await fn(principal, AuthorizerReader(authorizer))
