"""asunset_core — reusable platform primitives.

Consumer products import from here. Internal modules (asunset_core.auth.*,
asunset_core.audit.*, etc.) may be reorganized between minor versions.

See README.md for the intended usage patterns.
"""

from asunset_core.audit.events import EventType
from asunset_core.audit.redactor import (
    PassThroughRedactor,
    Redactor,
    get_redactor,
    set_redactor,
)
from asunset_core.audit.sink import AuditSink
from asunset_core.auth.authorizer import (
    AccessPath,
    Authorizer,
    OpenFGAAuthorizer,
    Tuple,
    make_openfga_client,
)
from asunset_core.auth.keycloak_admin import find_user_by_email
from asunset_core.auth.oidc import get_current_principal, require_platform_admin
from asunset_core.auth.principal import Principal
from asunset_core.db.models import (
    AppUser,
    AuditEvent,
    Base,
    MemberRole,
    Organization,
    OrgMember,
    Team,
    TeamMember,
)
from asunset_core.db.session import (
    get_admin_session_factory,
    get_db,
    get_engine,
    get_session_factory,
    session_scope,
)
from asunset_core.fga.bootstrap import bootstrap_openfga
from asunset_core.logging import configure_logging, get_logger
from asunset_core.middleware.correlation import CorrelationIdMiddleware

__all__ = [
    # auth
    "Principal",
    "get_current_principal",
    "require_platform_admin",
    "find_user_by_email",
    # authz
    "Authorizer",
    "OpenFGAAuthorizer",
    "AccessPath",
    "Tuple",
    "make_openfga_client",
    # audit
    "AuditSink",
    "EventType",
    "Redactor",
    "PassThroughRedactor",
    "set_redactor",
    "get_redactor",
    # db models
    "Base",
    "MemberRole",
    "Organization",
    "Team",
    "AppUser",
    "OrgMember",
    "TeamMember",
    "AuditEvent",
    # db session
    "get_engine",
    "get_session_factory",
    "get_admin_session_factory",
    "session_scope",
    "get_db",
    # middleware + logging + fga
    "CorrelationIdMiddleware",
    "configure_logging",
    "get_logger",
    "bootstrap_openfga",
]
