import { useState } from "react";
import { useAuth } from "react-oidc-context";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, Trash2 } from "lucide-react";

import { api, type Role, type Team } from "@/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function TeamsPage({ orgRole }: { orgRole: Role }) {
  const auth = useAuth();
  const f = { accessToken: auth.user?.access_token };
  const qc = useQueryClient();

  const isOrgAdmin = orgRole === "admin";
  const [newName, setNewName] = useState("");

  const teamsQ = useQuery({
    queryKey: ["teams"],
    queryFn: () => api.listTeams(f),
  });

  const createM = useMutation({
    mutationFn: () => api.createTeam(f, { name: newName.trim() }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["teams"] });
      setNewName("");
    },
  });

  const deleteM = useMutation({
    mutationFn: (id: string) => api.deleteTeam(f, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["teams"] }),
  });

  return (
    <div className="space-y-6 max-w-4xl">
      <h1 className="text-2xl font-semibold">Teams</h1>

      {isOrgAdmin && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Create team</CardTitle>
          </CardHeader>
          <CardContent className="flex items-end gap-2">
            <div className="flex-1 space-y-2">
              <Label htmlFor="new-team">Name</Label>
              <Input
                id="new-team"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Cardiology"
              />
            </div>
            <Button
              onClick={() => createM.mutate()}
              disabled={newName.trim().length === 0 || createM.isPending}
            >
              {createM.isPending ? "Creating…" : "Create"}
            </Button>
          </CardContent>
          {createM.error && (
            <CardContent className="pt-0 text-sm text-destructive">
              {(createM.error as Error).message}
            </CardContent>
          )}
        </Card>
      )}

      {teamsQ.isLoading && <p className="text-muted-foreground">Loading…</p>}
      {teamsQ.error && (
        <p className="text-sm text-destructive">
          {(teamsQ.error as Error).message}
        </p>
      )}
      {teamsQ.data?.length === 0 && (
        <p className="text-muted-foreground">No teams yet.</p>
      )}

      <div className="space-y-3">
        {teamsQ.data?.map((team) => (
          <TeamRow
            key={team.id}
            team={team}
            isOrgAdmin={isOrgAdmin}
            onDelete={() => deleteM.mutate(team.id)}
            deleting={deleteM.isPending}
          />
        ))}
      </div>
    </div>
  );
}

function TeamRow({
  team,
  isOrgAdmin,
  onDelete,
  deleting,
}: {
  team: Team;
  isOrgAdmin: boolean;
  onDelete: () => void;
  deleting: boolean;
}) {
  const [open, setOpen] = useState(false);
  return (
    <Card>
      <div className="flex items-center justify-between px-6 py-4">
        <button
          className="flex items-center gap-2 flex-1 text-left"
          onClick={() => setOpen((v) => !v)}
        >
          {open ? (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-4 w-4 text-muted-foreground" />
          )}
          <span className="font-medium">{team.name}</span>
        </button>
        {isOrgAdmin && (
          <Button
            size="sm"
            variant="ghost"
            onClick={onDelete}
            disabled={deleting}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        )}
      </div>
      {open && <TeamMembersPanel team={team} canManage={isOrgAdmin} />}
    </Card>
  );
}

function TeamMembersPanel({
  team,
  canManage,
}: {
  team: Team;
  canManage: boolean;
}) {
  const auth = useAuth();
  const f = { accessToken: auth.user?.access_token };
  const qc = useQueryClient();

  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("member");

  const membersQ = useQuery({
    queryKey: ["team-members", team.id],
    queryFn: () => api.listTeamMembers(f, team.id),
  });

  const addM = useMutation({
    mutationFn: async () => {
      const user = await api.lookupUser(f, email.trim());
      return api.addTeamMember(f, team.id, { user_id: user.id, role });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["team-members", team.id] });
      setEmail("");
    },
  });

  const removeM = useMutation({
    mutationFn: (userId: string) => api.removeTeamMember(f, team.id, userId),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["team-members", team.id] }),
  });

  return (
    <CardContent className="border-t pt-4 space-y-4">
      {membersQ.isLoading && <p className="text-muted-foreground text-sm">Loading members…</p>}
      {membersQ.data && membersQ.data.length === 0 && (
        <p className="text-muted-foreground text-sm">No members yet.</p>
      )}

      <ul className="divide-y">
        {membersQ.data?.map((m) => (
          <li key={m.user.id} className="flex items-center justify-between py-2">
            <div>
              <div className="text-sm font-medium">{m.user.display_name}</div>
              <div className="text-xs text-muted-foreground">
                {m.user.email} · {m.role}
              </div>
            </div>
            {canManage && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => removeM.mutate(m.user.id)}
                disabled={removeM.isPending}
              >
                Remove
              </Button>
            )}
          </li>
        ))}
      </ul>

      {canManage && (
        <div className="flex items-end gap-2 pt-2 border-t">
          <div className="flex-1 space-y-2">
            <Label htmlFor={`add-${team.id}`}>Add by email</Label>
            <Input
              id={`add-${team.id}`}
              type="email"
              placeholder="bob@asunset.local"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor={`role-${team.id}`}>Role</Label>
            <select
              id={`role-${team.id}`}
              className="rounded-md border border-input bg-background h-10 px-2 text-sm"
              value={role}
              onChange={(e) => setRole(e.target.value as Role)}
            >
              <option value="member">member</option>
              <option value="admin">admin</option>
            </select>
          </div>
          <Button
            onClick={() => addM.mutate()}
            disabled={email.trim().length === 0 || addM.isPending}
          >
            {addM.isPending ? "Adding…" : "Add"}
          </Button>
        </div>
      )}
      {(addM.error || removeM.error) && (
        <p className="text-sm text-destructive">
          {((addM.error ?? removeM.error) as Error).message}
        </p>
      )}
    </CardContent>
  );
}
