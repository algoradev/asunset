import { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  AsunsetAuthProvider,
  createApiCore,
  createOidcConfig,
  createPlatformClient,
  useAuth,
  useFetcher,
  useIdleLogout,
  useSilentBootstrap,
  type Me,
  type OrgMember,
} from "@asunset/web-sdk";

const oidcConfig = createOidcConfig({
  keycloakUrl: "http://localhost:8080",
  realm: "asunset",
  clientId: "asunset-web",
});

function LoginScreen({ onSignIn }: { onSignIn: () => void }) {
  return (
    <main>
      <h1>Foreign UI Min</h1>
      <p>Signed out.</p>
      <button type="button" onClick={onSignIn}>
        Sign in
      </button>
    </main>
  );
}

function IdleWarning({
  secondsLeft,
  onStaySignedIn,
}: {
  secondsLeft: number;
  onStaySignedIn: () => void;
}) {
  return (
    <div role="dialog" aria-modal="true" aria-labelledby="idle-title">
      <h2 id="idle-title">Idle timeout</h2>
      <p>Signing out in {secondsLeft} seconds.</p>
      <button type="button" onClick={onStaySignedIn}>
        Stay signed in
      </button>
    </div>
  );
}

function DataView() {
  const auth = useAuth();
  const fetcher = useFetcher();
  const platform = useMemo(() => createPlatformClient(createApiCore("")), []);
  const [me, setMe] = useState<Me | null>(null);
  const [members, setMembers] = useState<OrgMember[]>([]);
  const [error, setError] = useState<string | null>(null);
  const idle = useIdleLogout({
    enabled: auth.isAuthenticated,
    onLogout: () => {
      void auth.signoutRedirect();
    },
  });

  useEffect(() => {
    let alive = true;
    setError(null);
    void Promise.all([platform.me(fetcher), platform.listOrgMembers(fetcher)])
      .then(([nextMe, nextMembers]) => {
        if (!alive) return;
        setMe(nextMe);
        setMembers(nextMembers);
      })
      .catch((err: unknown) => {
        if (!alive) return;
        setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      alive = false;
    };
  }, [fetcher, platform]);

  return (
    <main>
      <h1>Foreign UI Min</h1>
      <button
        type="button"
        onClick={() => {
          void auth.signoutRedirect();
        }}
      >
        Sign out
      </button>

      {idle.warning ? (
        <IdleWarning secondsLeft={idle.secondsLeft} onStaySignedIn={idle.reset} />
      ) : null}

      {error ? <p role="alert">API error: {error}</p> : null}

      <section>
        <h2>Me</h2>
        <pre>{me ? JSON.stringify(me, null, 2) : "Loading..."}</pre>
      </section>

      <section>
        <h2>Org members</h2>
        <ul>
          {members.map((member) => (
            <li key={member.user.id}>
              {member.user.display_name} ({member.user.email}) - {member.role}
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}

function Gate() {
  const auth = useAuth();
  const silent = useSilentBootstrap();

  if (auth.isLoading || silent === "trying") {
    return <main>Loading...</main>;
  }
  if (!auth.isAuthenticated) {
    return <LoginScreen onSignIn={() => void auth.signinRedirect()} />;
  }
  return <DataView />;
}

createRoot(document.getElementById("root") as HTMLElement).render(
  <AsunsetAuthProvider config={oidcConfig}>
    <Gate />
  </AsunsetAuthProvider>,
);
