import { Fragment, useCallback, useState } from "react";
import { useAuth } from "react-oidc-context";
import { useQuery } from "@tanstack/react-query";

import { api } from "./api";
import { BRAND } from "./config/brand";
import { RESOURCE } from "./config/resource";
import { CONSUMER_ROUTES } from "./config/routes";
import { useT } from "./lib/useT";
import { AppSidebar } from "./components/app-sidebar";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "./components/ui/breadcrumb";
import { Button } from "./components/ui/button";
import { IdleWarningDialog } from "./components/IdleWarningDialog";
import { LogoutConfirmDialog } from "./components/LogoutConfirmDialog";
import { LoginForm } from "./components/login-form";
import { Separator } from "./components/ui/separator";
import { Spinner } from "./components/ui/spinner";
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "./components/ui/sidebar";
import { BootstrapGate } from "./features/bootstrap/BootstrapGate";
import { NotesPage } from "./features/notes/NotesPage";
import { TeamsPage } from "./features/teams/TeamsPage";
import { OrgPage } from "./features/org/OrgPage";
import { AuditPage } from "./features/audit/AuditPage";
import { AdminPage } from "./features/admin/AdminPage";
import { CommandPalette } from "./components/CommandPalette";
import { SettingsDialog } from "./components/settings/SettingsDialog";
import {
  SettingsProvider,
  useSettings,
} from "./components/settings/SettingsContext";
import type { Route } from "./lib/route";
import { useRoute } from "./lib/route";
import { useIdleLogout } from "./lib/useIdleLogout";

export default function App() {
  const auth = useAuth();
  const { t } = useT();

  if (auth.isLoading) return <CenteredSpinner label={t("common.loading")} />;

  if (!auth.isAuthenticated) {
    return (
      <LoginShell>
        <LoginForm
          onSignIn={() => auth.signinRedirect()}
          error={auth.error?.message}
        />
      </LoginShell>
    );
  }

  return <AuthedShell />;
}

function LoginShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/40 p-6">
      <div className="w-full max-w-sm rounded-lg border bg-card p-8 shadow-sm">
        {children}
      </div>
    </div>
  );
}

function AuthedShell() {
  const auth = useAuth();
  const { t } = useT();
  const token = auth.user?.access_token;
  const f = { accessToken: token };
  const [route, navigate] = useRoute();

  // HIPAA §164.312(a)(2)(iii): terminate inactive sessions. 15min idle +
  // 1min warning aligns with Keycloak's ssoSessionIdleTimeout=900s so
  // the UI logs out before the server starts 401'ing. Idle-timeout logout
  // is unconditional — no confirmation dialog — because we must sign out
  // within the grace window regardless of what the user is doing.
  const forceLogout = useCallback(() => auth.signoutRedirect(), [auth]);
  const idle = useIdleLogout({
    idleMinutes: 15,
    warningMinutes: 1,
    onLogout: forceLogout,
    enabled: true,
  });

  // User-triggered sign-out goes through a confirmation dialog. All
  // entrypoints (sidebar popover, ⌘K palette, Settings → Security) call
  // requestLogout; the confirm button calls forceLogout.
  const [logoutConfirmOpen, setLogoutConfirmOpen] = useState(false);
  const requestLogout = useCallback(() => setLogoutConfirmOpen(true), []);

  const meQ = useQuery({
    queryKey: ["me"],
    queryFn: () => api.me(f),
    enabled: !!token,
  });

  if (meQ.isLoading)
    return <CenteredSpinner label={t("common.loadingAccount")} />;
  if (meQ.error) {
    return (
      <Centered>
        <div className="space-y-2 text-center">
          <p>{t("common.cannotLoadAccount")}</p>
          <p className="text-sm text-muted-foreground">
            {(meQ.error as Error).message}
          </p>
          <Button variant="outline" onClick={() => auth.signoutRedirect()}>
            {t("common.signOut")}
          </Button>
        </div>
      </Centered>
    );
  }

  const me = meQ.data!;
  const isPlatformAdmin = me.realm_roles.includes("platform_admin");

  if (me.org_id === null) {
    // Pre-bootstrap: no sidebar, just the gate. There's nothing useful
    // to navigate to until the org exists.
    return (
      <Centered>
        <div className="w-full max-w-xl space-y-4">
          <h1 className="text-center text-2xl font-semibold">{BRAND.name}</h1>
          <BootstrapGate isPlatformAdmin={isPlatformAdmin} />
        </div>
        <IdleWarningDialog
          open={idle.warning}
          secondsLeft={idle.secondsLeft}
          onStay={idle.reset}
          onSignOutNow={forceLogout}
        />
      </Centered>
    );
  }

  return (
    <SettingsProvider me={me} onRequestLogout={requestLogout}>
      <SidebarProvider>
        <PaletteWithSettings
          isPlatformAdmin={isPlatformAdmin}
          orgRole={me.org_role}
          onNavigate={navigate}
          onSignOut={requestLogout}
        />
        <SettingsDialog />
        <LogoutConfirmDialog
          open={logoutConfirmOpen}
          onOpenChange={setLogoutConfirmOpen}
          onConfirm={() => {
            setLogoutConfirmOpen(false);
            forceLogout();
          }}
        />
        <AppSidebar
          me={me}
          route={route}
          onNavigate={navigate}
          onSignOut={requestLogout}
        />
      <SidebarInset>
        <header className="flex h-12 shrink-0 items-center gap-2 border-b bg-background">
          <div className="flex w-full items-center gap-2 px-4 lg:px-6">
            <SidebarTrigger className="-ml-1" />
            <Separator orientation="vertical" className="mx-1 h-4" />
            <Breadcrumb>
              <BreadcrumbList>
                <BreadcrumbItem className="hidden sm:inline-flex">
                  <BreadcrumbLink
                    href="#"
                    onClick={(e) => {
                      e.preventDefault();
                      navigate(RESOURCE.routeKey);
                    }}
                  >
                    {BRAND.name}
                  </BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator className="hidden sm:inline-flex" />
                <BreadcrumbItem>
                  <BreadcrumbPage className="text-sm font-medium">
                    {pageTitle(route, t)}
                  </BreadcrumbPage>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </div>
        </header>
        <main className="@container/main flex flex-1 flex-col gap-4 py-6 md:gap-6">
          {route === RESOURCE.routeKey && <NotesPage />}
          {route === "teams" && <TeamsPage orgRole={me.org_role!} />}
          {route === "org" && <OrgPage orgRole={me.org_role!} />}
          {route === "audit" && <AuditPage orgRole={me.org_role!} />}
          {route === "admin" && isPlatformAdmin && <AdminPage />}
          {CONSUMER_ROUTES.map((r) =>
            route === r.key &&
            (!r.visible || r.visible({ isPlatformAdmin, orgRole: me.org_role })) ? (
              <Fragment key={r.key}>{r.page}</Fragment>
            ) : null,
          )}
        </main>
      </SidebarInset>
        <IdleWarningDialog
          open={idle.warning}
          secondsLeft={idle.secondsLeft}
          onStay={idle.reset}
          onSignOutNow={forceLogout}
        />
      </SidebarProvider>
    </SettingsProvider>
  );
}

function PaletteWithSettings(props: {
  isPlatformAdmin: boolean;
  orgRole: "admin" | "member" | null;
  onNavigate: (r: Route) => void;
  onSignOut: () => void;
}) {
  const { openSettings } = useSettings();
  return (
    <CommandPalette
      isPlatformAdmin={props.isPlatformAdmin}
      orgRole={props.orgRole}
      onNavigate={props.onNavigate}
      onSignOut={props.onSignOut}
      onOpenSettings={openSettings}
    />
  );
}

function pageTitle(route: Route, t: (k: string) => string): string {
  if (route === RESOURCE.routeKey) return t("nav.notes");
  if (route === "teams") return t("nav.teams");
  if (route === "org") return t("nav.org");
  if (route === "audit") return t("nav.audit");
  if (route === "admin") return t("nav.admin");
  const consumerRoute = CONSUMER_ROUTES.find((r) => r.key === route);
  if (consumerRoute) return t(consumerRoute.labelKey);
  return BRAND.name;
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen grid place-items-center bg-background text-foreground p-6">
      {children}
    </div>
  );
}

function CenteredSpinner({ label }: { label: string }) {
  return (
    <Centered>
      <div className="flex items-center gap-3 text-muted-foreground">
        <Spinner className="size-5" />
        <span className="text-sm">{label}</span>
      </div>
    </Centered>
  );
}
