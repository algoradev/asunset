import { useCallback } from "react";
import { useAuth } from "react-oidc-context";
import { useQuery } from "@tanstack/react-query";

import { api } from "./api";
import { Button } from "./components/ui/button";
import { IdleWarningDialog } from "./components/IdleWarningDialog";
import { Sidebar } from "./components/Sidebar";
import { BootstrapGate } from "./features/bootstrap/BootstrapGate";
import { NotesPage } from "./features/notes/NotesPage";
import { TeamsPage } from "./features/teams/TeamsPage";
import { OrgPage } from "./features/org/OrgPage";
import { AuditPage } from "./features/audit/AuditPage";
import { AdminPage } from "./features/admin/AdminPage";
import { useRoute } from "./lib/route";
import { useIdleLogout } from "./lib/useIdleLogout";

export default function App() {
  const auth = useAuth();

  if (auth.isLoading) return <Centered>Loading…</Centered>;
  if (auth.error)
    return <Centered>Auth error: {auth.error.message}</Centered>;

  if (!auth.isAuthenticated) {
    return (
      <Centered>
        <div className="space-y-4 text-center">
          <h1 className="text-2xl font-semibold">Asunset</h1>
          <p className="text-muted-foreground">Sign in with Keycloak to continue.</p>
          <Button onClick={() => auth.signinRedirect()}>Sign in</Button>
        </div>
      </Centered>
    );
  }

  return <AuthedShell />;
}

function AuthedShell() {
  const auth = useAuth();
  const token = auth.user?.access_token;
  const f = { accessToken: token };
  const [route, navigate] = useRoute();

  // HIPAA §164.312(a)(2)(iii): terminate inactive sessions. 15min idle +
  // 1min warning aligns with Keycloak's ssoSessionIdleTimeout=900s so
  // the UI logs out before the server starts 401'ing.
  const forceLogout = useCallback(() => auth.signoutRedirect(), [auth]);
  const idle = useIdleLogout({
    idleMinutes: 15,
    warningMinutes: 1,
    onLogout: forceLogout,
    enabled: true,
  });

  const meQ = useQuery({
    queryKey: ["me"],
    queryFn: () => api.me(f),
    enabled: !!token,
  });

  if (meQ.isLoading) return <Centered>Loading account…</Centered>;
  if (meQ.error) {
    return (
      <Centered>
        <div className="space-y-2 text-center">
          <p>Could not load your account.</p>
          <p className="text-sm text-muted-foreground">
            {(meQ.error as Error).message}
          </p>
          <Button variant="outline" onClick={() => auth.signoutRedirect()}>
            Sign out
          </Button>
        </div>
      </Centered>
    );
  }

  const me = meQ.data!;
  const isPlatformAdmin = me.realm_roles.includes("platform_admin");

  if (me.org_id === null) {
    return (
      <TopShell me={me}>
        <BootstrapGate isPlatformAdmin={isPlatformAdmin} />
        <IdleWarningDialog
          open={idle.warning}
          secondsLeft={idle.secondsLeft}
          onStay={idle.reset}
          onSignOutNow={forceLogout}
        />
      </TopShell>
    );
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      <Header me={me} />
      <div className="flex">
        <Sidebar route={route} onNavigate={navigate} realmRoles={me.realm_roles} />
        <main className="flex-1 p-8">
          {route === "notes" && <NotesPage />}
          {route === "teams" && <TeamsPage orgRole={me.org_role!} />}
          {route === "org" && <OrgPage orgRole={me.org_role!} />}
          {route === "audit" && <AuditPage orgRole={me.org_role!} />}
          {route === "admin" && isPlatformAdmin && <AdminPage />}
        </main>
      </div>
      <IdleWarningDialog
        open={idle.warning}
        secondsLeft={idle.secondsLeft}
        onStay={idle.reset}
        onSignOutNow={forceLogout}
      />
    </div>
  );
}

function TopShell({
  me,
  children,
}: {
  me: { user: { email: string; display_name: string } };
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <Header me={me} />
      <main className="container py-8">{children}</main>
    </div>
  );
}

function Header({
  me,
}: {
  me: { user: { email: string; display_name: string } };
}) {
  const auth = useAuth();
  return (
    <header className="border-b">
      <div className="flex h-14 items-center justify-between px-6">
        <div className="font-semibold">Asunset</div>
        <div className="flex items-center gap-4 text-sm">
          <span className="text-muted-foreground">
            {me.user.display_name} · {me.user.email}
          </span>
          <Button size="sm" variant="outline" onClick={() => auth.signoutRedirect()}>
            Sign out
          </Button>
        </div>
      </div>
    </header>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen grid place-items-center bg-background text-foreground p-6">
      {children}
    </div>
  );
}
