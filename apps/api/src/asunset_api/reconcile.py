"""CLI entrypoint for `python -m asunset_api.reconcile`.

Designed for cron. Exits 0 when reconciliation completes (even if drift
was fixed — drift is expected under the dual-write model and is not an
error condition). Exits non-zero only when the job itself cannot run
(DB unreachable, FGA unreachable, etc.), so a failure in the scheduler
means something is actually broken.

Example cron line (daily at 02:17):
    17 2 * * *  docker compose exec -T api python -m asunset_api.reconcile
"""

from __future__ import annotations

import asyncio
import json
import sys

from sqlalchemy import text

from asunset_core.audit.sink import AuditSink
from asunset_core.auth.authorizer import OpenFGAAuthorizer, make_openfga_client
from asunset_api.config import get_settings
from asunset_core.db.session import get_admin_session_factory
from asunset_core.fga.bootstrap import bootstrap_openfga
from asunset_api.fga.reconcile import reconcile
from asunset_core.logging import configure_logging, get_logger

log = get_logger("asunset_api.reconcile")


async def _run() -> int:
    settings = get_settings()
    configure_logging(settings.api_log_level)
    log.info("reconcile.cli.start")

    store_id, model_id = await bootstrap_openfga(settings)
    client = make_openfga_client(settings, store_id, model_id)
    authorizer = OpenFGAAuthorizer(client, store_id, model_id)

    try:
        factory = get_admin_session_factory()
        async with factory() as session:
            # Admin session = schema owner = bypasses RLS (owner bypass,
            # since migrations don't set FORCE). Reconcile spans every org,
            # so RLS is a liability here.
            audit = AuditSink(session, org_id=None, actor_id=None, trace_id=None)
            report = await reconcile(authorizer, session, audit)
            await session.commit()
    finally:
        await client.close()

    print(json.dumps({
        "checked": report.checked,
        "missing_tuples": report.missing_tuples,
        "added_tuples": report.added_tuples,
        "drift_by_type": report.drift_by_type,
    }))
    return 0


def main() -> None:
    sys.exit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
