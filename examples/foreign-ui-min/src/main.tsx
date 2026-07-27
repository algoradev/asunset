import { useState } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  ApiError,
  AsunsetAuthProvider,
  createApiCore,
  createOidcConfig,
  createPlatformClient,
  useAuth,
  useIdleLogout,
  useSilentBootstrap,
} from "@asunset/web-sdk";
import { createPlatformHooks } from "@asunset/web-sdk/hooks";

const oidcConfig = createOidcConfig({
  keycloakUrl: "http://localhost:8080",
  realm: "asunset",
  clientId: "asunset-web",
});
const platform = createPlatformClient(createApiCore(""));
const queryClient = new QueryClient();
const {
  useCreateTeam,
  useDeleteTeam,
  useInviteMember,
  useMe,
  useOrgMembers,
  useTeams,
} = createPlatformHooks(platform);

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
  const meQ = useMe();
  const membersQ = useOrgMembers();
  const teamsQ = useTeams();
  const [teamName, setTeamName] = useState("");
  const [createdTeamId, setCreatedTeamId] = useState<string | null>(null);
  const [inviteCode, setInviteCode] = useState<string | null>(null);
  const createTeam = useCreateTeam({
    onSuccess: (team) => {
      setCreatedTeamId(team.id);
      setTeamName("");
    },
  });
  const deleteTeam = useDeleteTeam({
    onSuccess: () => setCreatedTeamId(null),
  });
  const inviteMember = useInviteMember({
    onError: (err) => {
      if (err instanceof ApiError && err.code === "already_a_member") {
        setInviteCode(err.code);
      } else if (err instanceof ApiError) {
        setInviteCode(err.code ?? `http_${err.status}`);
      } else {
        setInviteCode("unknown_error");
      }
    },
  });
  const idle = useIdleLogout({
    enabled: auth.isAuthenticated,
    onLogout: () => {
      void auth.signoutRedirect();
    },
  });
  const error = meQ.error ?? membersQ.error ?? teamsQ.error;
  const working = createTeam.isPending || deleteTeam.isPending || inviteMember.isPending;

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

      {error ? <p role="alert">API error: {String(error)}</p> : null}

      <section>
        <h2>Me</h2>
        <pre>{meQ.data ? JSON.stringify(meQ.data, null, 2) : "Loading..."}</pre>
      </section>

      <section>
        <h2>Org members</h2>
        <ul>
          {(membersQ.data ?? []).map((member) => (
            <li key={member.user.id}>
              {member.user.display_name} ({member.user.email}) - {member.role}
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2>Teams</h2>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            const name = teamName.trim();
            if (name) {
              createTeam.mutate({ name });
            }
          }}
        >
          <input
            aria-label="Team name"
            value={teamName}
            onChange={(event) => setTeamName(event.target.value)}
          />
          <button type="submit" disabled={working || !teamName.trim()}>
            Create team
          </button>
        </form>
        <ul>
          {(teamsQ.data ?? []).map((team) => (
            <li key={team.id}>
              {team.name}
              {team.id === createdTeamId ? (
                <button
                  type="button"
                  disabled={working}
                  onClick={() => deleteTeam.mutate({ teamId: team.id })}
                >
                  Delete created team
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2>Invite error</h2>
        <button
          type="button"
          disabled={working}
          onClick={() => {
            setInviteCode(null);
            inviteMember.mutate({ email: "alice@asunset.local", role: "member" });
          }}
        >
          Invite Alice
        </button>
        <p>Invite code: {inviteCode ?? "none"}</p>
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
  <QueryClientProvider client={queryClient}>
    <AsunsetAuthProvider config={oidcConfig}>
      <Gate />
    </AsunsetAuthProvider>
  </QueryClientProvider>,
);
