"""Authorizer port + default OpenFGA implementation.

The port stays deliberately small: `check`, `list_objects`, `write`. Routes
depend on this interface, not on the OpenFGA SDK, so swapping to a different
FGA store (Cerbos, SpiceDB, Permify) is a single-file adapter.

Object IDs follow OpenFGA's `type:id` convention as plain strings at the
port boundary. Callers build them with the helpers on each domain model
(e.g. `f"note:{note.id}"`); the port never inspects their structure.

=== Dual-write failure model (read this before touching routers) ===

We write both to Postgres and to OpenFGA in the same request. We do not
have distributed transactions. The ordering in every mutating route is:

    1. DB write (session.add / session.delete, then session.flush — the
       SQL is sent but the transaction is not yet committed).
    2. FGA write via this port (authorizer.write(...)).
    3. DB commit at the end of the request (handled by get_db).

The invariant this buys us:

    *Fail toward orphan FGA tuples, never toward phantom DB rows.*

    - If the FGA write fails, the DB transaction rolls back. Clean.
    - If the DB commit fails after the FGA write succeeded, an FGA tuple
      exists for a row that doesn't. These are harmless — they grant
      access to something the DB won't return, so the app surfaces a 404.
      The reconcile job sweeps them up.
    - The opposite failure (DB row exists with no FGA tuple) would make
      resources invisible to their own owner — a user-visible correctness
      bug, compliance-relevant under HIPAA. We avoid it by ordering.

Deletes follow the same ordering (DB-delete then FGA-delete), for the
same reason: if the FGA delete fails, the user sees a zombie id in
their list and gets a 404 on read. Annoying but safe. Reconcile fixes it.

Anyone adding a new mutating route: follow this ordering. If you can't,
say why in a comment at the call site.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from openfga_sdk import ClientConfiguration, OpenFgaClient, ReadRequestTupleKey
from openfga_sdk.client.models import (
    ClientCheckRequest,
    ClientListObjectsRequest,
    ClientTuple,
    ClientWriteRequest,
)
from openfga_sdk.credentials import CredentialConfiguration, Credentials
from openfga_sdk.exceptions import ApiException

from asunset_core.config import CoreSettings as Settings
from asunset_core.logging import get_logger

log = get_logger(__name__)


def _is_already_exists(exc: ApiException) -> bool:
    """OpenFGA returns HTTP 400 + write_failed_due_to_invalid_input
    when a tuple in a write batch already exists. The user-facing
    message is `cannot write a tuple which already exists`. We detect
    via the message text rather than the code so the same logic works
    against older servers whose code field was less specific.
    """
    if exc.status != 400:
        return False
    blob = (exc.error_message or "") + " " + str(getattr(exc, "body", "") or "")
    return "already exists" in blob.lower()


@dataclass(frozen=True, slots=True)
class Tuple:
    """A single FGA relationship tuple, `user` → `relation` → `object`."""

    user: str
    relation: str
    object: str


AccessPathKind = Literal[
    "direct",       # user has a direct grant tuple on the object
    "team",         # granted via membership of an intermediate team
    "organization", # granted via org-wide share
    "unknown",      # check succeeded but path couldn't be classified
]


@dataclass(frozen=True, slots=True)
class AccessPath:
    """How an authorization check resolved.

    `kind` says what *class* of grant provided the access; `via_relation`
    is the specific relation on the target (editor/viewer/owner/...);
    `via_object` is set for team/organization kinds and holds the
    FGA object id (`team:abc-123`, `organization:xyz`) that routed the
    grant — routers turn this into a human label for the audit row.
    """

    kind: AccessPathKind
    via_relation: str
    via_object: str | None = None


class Authorizer(Protocol):
    async def check(self, user: str, relation: str, object: str) -> bool: ...

    async def list_objects(
        self, user: str, relation: str, object_type: str
    ) -> list[str]: ...

    async def read_tuples(
        self,
        *,
        user: str | None = None,
        relation: str | None = None,
        object: str | None = None,
    ) -> list[Tuple]: ...

    async def explain(
        self, user: str, relation: str, object: str
    ) -> AccessPath | None: ...

    async def write(
        self,
        writes: list[Tuple] | None = None,
        deletes: list[Tuple] | None = None,
        *,
        tolerate_existing: bool = False,
    ) -> None: ...

    async def explain_note_access(self, user: str, note: str) -> str: ...


class OpenFGAAuthorizer:
    """Default `Authorizer` impl backed by an OpenFGA server.

    Holds the resolved `store_id` + `authorization_model_id` after bootstrap
    so every call goes to the same pinned model — operators roll forward
    by writing a new model and updating the env, never in-place.
    """

    def __init__(
        self,
        client: OpenFgaClient,
        store_id: str,
        model_id: str,
    ) -> None:
        self._client = client
        self._store_id = store_id
        self._model_id = model_id

    async def check(self, user: str, relation: str, object: str) -> bool:
        req = ClientCheckRequest(user=user, relation=relation, object=object)
        resp = await self._client.check(req)
        return bool(resp.allowed)

    async def list_objects(
        self, user: str, relation: str, object_type: str
    ) -> list[str]:
        req = ClientListObjectsRequest(user=user, relation=relation, type=object_type)
        resp = await self._client.list_objects(req)
        return list(resp.objects or [])

    async def read_tuples(
        self,
        *,
        user: str | None = None,
        relation: str | None = None,
        object: str | None = None,
    ) -> list[Tuple]:
        body = ReadRequestTupleKey(user=user, relation=relation, object=object)
        out: list[Tuple] = []
        # Paginate — important for large objects (e.g. a team with many notes).
        continuation: str | None = None
        while True:
            options: dict = {"page_size": 100}
            if continuation:
                options["continuation_token"] = continuation
            resp = await self._client.read(body, options=options)
            for t in resp.tuples or []:
                key = t.key
                out.append(Tuple(user=key.user, relation=key.relation, object=key.object))
            continuation = getattr(resp, "continuation_token", None)
            if not continuation:
                break
        return out

    async def write(
        self,
        writes: list[Tuple] | None = None,
        deletes: list[Tuple] | None = None,
        *,
        tolerate_existing: bool = False,
    ) -> None:
        """Apply tuple writes/deletes against the FGA store.

        `tolerate_existing` (writes only): when a retry might re-issue
        a tuple that already landed on a previous partially-failed
        attempt — e.g. the invite flow where DB-commit can fail after
        FGA-write succeeded — set this. The bulk write is tried first
        (fast path); if it raises with the OpenFGA "tuple already
        exists" 400, the writes are replayed one-at-a-time and that
        specific error is swallowed per-tuple. Other errors propagate.
        Deletes don't need this — OpenFGA already returns 200 when the
        tuple doesn't exist.
        """
        def to_client_tuples(ts: list[Tuple] | None) -> list[ClientTuple] | None:
            if not ts:
                return None
            return [ClientTuple(user=t.user, relation=t.relation, object=t.object) for t in ts]

        try:
            req = ClientWriteRequest(
                writes=to_client_tuples(writes),
                deletes=to_client_tuples(deletes),
            )
            await self._client.write(req)
            return
        except ApiException as exc:
            if not tolerate_existing or not writes or not _is_already_exists(exc):
                raise

        # Replay writes one at a time, swallowing only the duplicate-tuple
        # 400 so a half-applied prior attempt doesn't block retry.
        for t in writes:
            try:
                await self._client.write(
                    ClientWriteRequest(writes=[ClientTuple(user=t.user, relation=t.relation, object=t.object)])
                )
            except ApiException as exc:
                if _is_already_exists(exc):
                    log.info(
                        "fga.write.tolerated_existing",
                        extra={"user": t.user, "relation": t.relation, "object": t.object},
                    )
                    continue
                raise
        # Deletes only run if the bulk write succeeded above; this fallback
        # path is writes-only by design (deletes already idempotent in FGA).

    async def explain(
        self, user: str, relation: str, object: str
    ) -> AccessPath | None:
        """Classify which grant satisfied a successful check.

        Enumerates every tuple on the object, then for each tuple decides:
          * direct user grant — user field matches the caller verbatim;
          * userset grant (`team:X#member`, `organization:Y#member`) —
            the caller satisfies it iff they hold the reciprocal relation
            on the parent object, verified via a `check` call.

        Returns the first matching path (objects don't usually have more
        than a handful of grants). Returns None if the caller arrives
        via a path we don't recognize — routers treat that as "unknown"
        rather than erroring, so audit rows stay honest.
        """
        grants = await self.read_tuples(object=object)
        for t in grants:
            if t.user == user:
                return AccessPath(kind="direct", via_relation=t.relation)

            if "#" not in t.user:
                continue

            parent_object, parent_relation = t.user.split("#", 1)
            if ":" not in parent_object:
                continue
            parent_type = parent_object.split(":", 1)[0]

            if await self.check(user, parent_relation, parent_object):
                kind: AccessPathKind = (
                    "team" if parent_type == "team"
                    else "organization" if parent_type == "organization"
                    else "unknown"
                )
                return AccessPath(
                    kind=kind,
                    via_relation=t.relation,
                    via_object=parent_object,
                )

        return None

    async def explain_note_access(self, user: str, note: str) -> str:
        """Classify HOW a user was granted access to a note.

        Returns one of: owner, direct_editor, direct_viewer,
        team_editor, team_viewer, org_viewer, or "unknown" if none of
        the expected paths resolve.

        Order matters — we return the most specific match first, which
        gives auditors a single clear answer even when a user qualifies
        via multiple paths ("owner AND team_viewer" collapses to "owner").

        Cost: 1–4 FGA reads depending on how specific the grant is.
        For resources with many team/org grants, the later branches
        pay a read-all-tuples-on-object fee; acceptable for audit paths
        on individual resource access.
        """
        # 1. Direct owner
        if await self.read_tuples(user=user, relation="owner", object=note):
            return "owner"
        # 2. Direct editor / viewer (explicit user:X tuples)
        if await self.read_tuples(user=user, relation="editor", object=note):
            return "direct_editor"
        if await self.read_tuples(user=user, relation="viewer", object=note):
            return "direct_viewer"

        # 3. Team / org grants — enumerate grants on the object and
        # evaluate each against the user. Doing reads rather than checks
        # because we need the *grant identity* to label the path.
        all_grants = await self.read_tuples(object=note)
        team_editor_grants = [
            t for t in all_grants
            if t.relation == "editor" and t.user.endswith("#member")
        ]
        team_viewer_grants = [
            t for t in all_grants
            if t.relation == "viewer" and t.user.endswith("#member")
        ]

        async def user_resolves_through(t: Tuple) -> bool:
            # t.user looks like "team:abc#member" or "organization:abc#member".
            # The full userset is satisfied if the user is a direct member
            # of that team/organization.
            subject, _, relation = t.user.partition("#")
            return await self.check(user=user, relation=relation, object=subject)

        for t in team_editor_grants:
            if t.user.startswith("team:") and await user_resolves_through(t):
                return "team_editor"
        for t in team_viewer_grants:
            if t.user.startswith("team:") and await user_resolves_through(t):
                return "team_viewer"
        for t in team_viewer_grants:
            if t.user.startswith("organization:") and await user_resolves_through(t):
                return "org_viewer"

        return "unknown"


def make_openfga_client(settings: Settings, store_id: str, model_id: str) -> OpenFgaClient:
    """Build the SDK client authenticated with the preshared API key.

    The server side (compose.yml's openfga service) holds the same key
    in OPENFGA_AUTHN_PRESHARED_KEYS. Rotation: change OPENFGA_API_KEY
    in .env and restart both containers together.
    """
    config = ClientConfiguration(
        api_url=settings.openfga_api_url,
        store_id=store_id,
        authorization_model_id=model_id,
        credentials=Credentials(
            method="api_token",
            configuration=CredentialConfiguration(api_token=settings.openfga_api_key),
        ),
    )
    return OpenFgaClient(config)
