"""The demo's scope resolvers (spec §11 reference; consumers mirror
this file as authz/scopes.py-style code next to their authorization
logic — never inside product/methodology folders).

Registered at startup; the manifest references these by name; startup
validation fails loud on a declared-but-unregistered resolver, same
posture as gate-key validation.
"""

from __future__ import annotations

from asunset_core.auth.principal import Principal
from asunset_core.features import AuthorizerReader, scope_registry


async def visible_notes(principal: Principal, reader: AuthorizerReader) -> list[str]:
    """Everything the caller may view — owned notes INCLUDED, because
    ownership derives can_view through the FGA model (the fact caliper's
    exercise-1 defensive owner-union existed to not-know)."""
    objs = await reader.list_objects(principal.fga_user(), "can_view", "note")
    return [o.removeprefix("note:") for o in objs]


def register_scopes() -> None:
    scope_registry().register("note", "visible_notes", visible_notes)
