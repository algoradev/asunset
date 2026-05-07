import { useState } from "react";
import { useAuth } from "react-oidc-context";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2 } from "lucide-react";
import { toast } from "sonner";

import { api, type Role } from "@/api";
import { AddMemberRow } from "@/components/AddMemberRow";
import { CopyButton } from "@/components/CopyButton";
import { MemberTable } from "@/components/MemberTable";
import { PageHeader } from "@/components/PageHeader";
import { useT } from "@/lib/useT";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/States";

export function OrgPage({ orgRole }: { orgRole: Role }) {
  const auth = useAuth();
  const { t } = useT();
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
      toast.success(t("org.memberAdded"));
    },
    onError: (e) => toast.error((e as Error).message),
  });

  const updateRoleM = useMutation({
    mutationFn: ({ userId, newRole }: { userId: string; newRole: Role }) =>
      api.updateOrgMemberRole(f, userId, newRole),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["org-members"] });
      toast.success(t("org.roleUpdated", { role: vars.newRole }));
    },
    onError: (e) => toast.error((e as Error).message),
  });

  const removeM = useMutation({
    mutationFn: (userId: string) => api.removeOrgMember(f, userId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["org-members"] });
      toast.success(t("org.memberRemoved"));
    },
    onError: (e) => toast.error((e as Error).message),
  });

  return (
    <div className="page-container">
      <PageHeader title={t("org.title")} description={t("org.description")} />

      <Card size="sm">
        <CardContent className="flex items-start gap-4">
          <div className="flex size-10 shrink-0 items-center justify-center rounded-md bg-muted">
            <Building2 className="size-5 text-muted-foreground" />
          </div>
          <div className="flex flex-col gap-1">
            <div className="text-card-title">{orgQ.data?.name ?? "—"}</div>
            <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-caption">
              <span>
                {t("org.created", {
                  when: orgQ.data?.created_at
                    ? new Date(orgQ.data.created_at).toLocaleDateString()
                    : "—",
                })}
              </span>
              <span className="inline-flex items-center gap-1 font-mono">
                {t("org.idLabel", { id: orgQ.data?.id ?? "—" })}
                {orgQ.data?.id && <CopyButton value={orgQ.data.id} />}
              </span>
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="flex flex-col gap-3">
        <div className="flex items-baseline justify-between">
          <h2 className="text-section-title">{t("common.members")}</h2>
          {membersQ.data && (
            <span className="text-caption">
              {t("common.member", { count: membersQ.data.length })}
            </span>
          )}
        </div>

        {!isAdmin && (
          <p className="text-caption">{t("org.nonAdminHint")}</p>
        )}

        {membersQ.isLoading && (
          <div className="rounded-lg border bg-card p-3 space-y-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="flex items-center gap-3 py-1">
                <Skeleton className="size-7 rounded-full" />
                <div className="flex-1 space-y-1">
                  <Skeleton className="h-4 w-40" />
                  <Skeleton className="h-3 w-56" />
                </div>
              </div>
            ))}
          </div>
        )}
        {membersQ.error && (
          <ErrorState
            error={membersQ.error}
            onRetry={() => membersQ.refetch()}
          />
        )}
        {membersQ.data && membersQ.data.length > 0 && (
          <MemberTable
            rows={membersQ.data}
            onRoleChange={
              isAdmin
                ? (userId, newRole) =>
                    updateRoleM.mutate({ userId, newRole })
                : undefined
            }
            roleBusy={
              updateRoleM.isPending
                ? (updateRoleM.variables?.userId ?? null)
                : null
            }
            actions={
              isAdmin
                ? (m) => (
                    <AlertDialog>
                      <AlertDialogTrigger asChild>
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={removeM.isPending}
                          className="text-muted-foreground hover:text-destructive"
                        >
                          {t("common.remove")}
                        </Button>
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>
                            {t("org.removeMemberTitle", {
                              name: m.user.display_name,
                            })}
                          </AlertDialogTitle>
                          <AlertDialogDescription>
                            {t("org.removeMemberDesc")}
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>
                            {t("common.cancel")}
                          </AlertDialogCancel>
                          <AlertDialogAction
                            className={buttonVariants({ variant: "destructive" })}
                            onClick={() => removeM.mutate(m.user.id)}
                          >
                            {t("common.remove")}
                          </AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  )
                : undefined
            }
          />
        )}
        {membersQ.data && membersQ.data.length === 0 && (
          <p className="text-sm text-muted-foreground">
            {t("org.noMembersYet")}
          </p>
        )}

        {isAdmin && (
          <div className="rounded-lg border bg-card p-4">
            <AddMemberRow
              inputId="org-add-email"
              roleId="org-add-role"
              email={email}
              onEmailChange={setEmail}
              role={role}
              onRoleChange={setRole}
              onSubmit={() => addM.mutate()}
              busy={addM.isPending}
            />
          </div>
        )}
      </div>
    </div>
  );
}
