"""The demo's scope resolvers (spec §11 reference; consumers mirror
this file as authz/scopes.py-style code next to their authorization
logic — never inside product/methodology folders).

Registered at startup; the manifest references these by name; startup
validation fails loud on a declared-but-unregistered resolver, same
posture as gate-key validation.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from asunset_core.auth.principal import Principal
from asunset_core.features import AuthorizerReader, scope_registry

ScopeFn = Callable[[Principal, AuthorizerReader], Awaitable[list[str]]]


async def visible_notes(principal: Principal, reader: AuthorizerReader) -> list[str]:
    """Everything the caller may view — owned notes INCLUDED, because
    ownership derives can_view through the FGA model (the fact caliper's
    exercise-1 defensive owner-union existed to not-know)."""
    objs = await reader.list_objects(principal.fga_user(), "can_view", "note")
    return [o.removeprefix("note:") for o in objs]


async def shareable_notes(principal: Principal, reader: AuthorizerReader) -> list[str]:
    """Notes the caller may manage shares for.

    Sharing is currently protected by `can_delete` in the Notes app business
    logic, so the capability reach follows that same FGA relation instead of
    reusing visible_notes. A viewer may see a note without being allowed to
    share it onward.
    """
    objs = await reader.list_objects(principal.fga_user(), "can_delete", "note")
    return [o.removeprefix("note:") for o in objs]


def _register_once(resource_type: str, name: str, fn: ScopeFn) -> None:
    registry = scope_registry()
    if (resource_type, name) not in registry.known():
        registry.register(resource_type, name, fn)


def register_scopes() -> None:
    _register_once("note", "visible_notes", visible_notes)
    _register_once("note", "shareable_notes", shareable_notes)
