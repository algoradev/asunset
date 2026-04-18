import { useState } from "react";
import { useAuth } from "react-oidc-context";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, type Role } from "@/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function OrgPage({ orgRole }: { orgRole: Role }) {
  const auth = useAuth();
  const f = { accessToken: auth.user?.access_token };
  const qc = useQueryClient();

  const isAdmin = orgRole === "admin";
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("member");

  const orgQ = useQuery({
    queryKey: ["org"],
    queryFn: () => api.getOrg(f),
  });
  const membersQ = useQuery({
    queryKey: ["org-members"],
    queryFn: () => api.listOrgMembers(f),
  });

  const addM = useMutation({
    mutationFn: async () => {
      const user = await api.lookupUser(f, email.trim());
      return api.addOrgMember(f, { user_id: user.id, role });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["org-members"] });
      setEmail("");
    },
  });

  const removeM = useMutation({
    mutationFn: (userId: string) => api.removeOrgMember(f, userId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["org-members"] }),
  });

  return (
    <div className="space-y-6 max-w-3xl">
      <h1 className="text-2xl font-semibold">Organization</h1>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{orgQ.data?.name ?? "—"}</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          Created{" "}
          {orgQ.data?.created_at
            ? new Date(orgQ.data.created_at).toLocaleString()
            : "—"}
          <div className="mt-1 font-mono text-xs">id: {orgQ.data?.id}</div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Members</CardTitle>
          {!isAdmin && (
            <p className="text-xs text-muted-foreground">
              Showing members you share a team with. Use the share-by-email
              flow to grant access to anyone else in the organization.
            </p>
          )}
        </CardHeader>
        <CardContent className="space-y-4">
          {membersQ.isLoading && (
            <p className="text-muted-foreground text-sm">Loading…</p>
          )}
          <ul className="divide-y">
            {membersQ.data?.map((m) => (
              <li
                key={m.user.id}
                className="flex items-center justify-between py-2"
              >
                <div>
                  <div className="text-sm font-medium">
                    {m.user.display_name}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {m.user.email} · {m.role} · joined{" "}
                    {new Date(m.joined_at).toLocaleDateString()}
                  </div>
                </div>
                {isAdmin && (
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

          {isAdmin && (
            <div className="flex items-end gap-2 pt-2 border-t">
              <div className="flex-1 space-y-2">
                <Label htmlFor="org-add-email">Add by email</Label>
                <Input
                  id="org-add-email"
                  type="email"
                  placeholder="bob@asunset.local"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="org-add-role">Role</Label>
                <select
                  id="org-add-role"
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
      </Card>
    </div>
  );
}
