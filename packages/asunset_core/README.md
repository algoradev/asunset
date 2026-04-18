# asunset-core

Reusable platform primitives extracted from the asunset template. Consumer
products (analytics platforms, internal admin tools, etc.) depend on this
package to inherit:

- **OIDC / JWT validation** keyed to the platform's Keycloak
- **`Authorizer` port + OpenFGA implementation** for ReBAC checks
- **`AuditSink`** with identity snapshotting + redactor hook
- **Correlation-ID middleware**
- **RLS-scoped SQLAlchemy session helpers** (app-role + admin-role)
- **Alembic-compatible `Base`** with the `audit_event` table
- **FGA bootstrap** to ensure a store exists on startup

The demo Notes app in `apps/api` uses this package for exactly the same
reasons a consumer product would — the foundation eats its own dog food.

## Public interface

Everything callable lives under the top-level `asunset_core` namespace:

```python
from asunset_core import (
    # auth
    Principal, get_current_principal, require_platform_admin,
    # authz
    Authorizer, OpenFGAAuthorizer, AccessPath, Tuple, make_openfga_client,
    # audit
    AuditSink, EventType, Redactor, set_redactor,
    # middleware
    CorrelationIdMiddleware,
    # db
    Base, AuditEvent, session_scope, get_session_factory, get_admin_session_factory,
    # logging
    configure_logging, get_logger,
)
```

Internal modules (`asunset_core.auth.oidc` etc.) are not part of the public
contract and can be reorganized between minor versions; always import from
the top-level package.
