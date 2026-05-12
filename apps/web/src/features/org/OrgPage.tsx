import { useState } from "react";
import { useAuth } from "react-oidc-context";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, MoreHorizontal } from "lucide-react";
import { toast } from "sonner";

import { api, type Role } from "@/api";
import { CopyButton } from "@/components/CopyButton";
import { MemberTable, type MemberRow } from "@/components/MemberTable";
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
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/States";
import { InviteMemberDialog } from "./InviteMemberDialog";
import { TempPasswordCallout } from "./TempPasswordCallout";

export function OrgPage({ orgRole }: { orgRole: Role }) {
  const auth = useAuth();
  const { t } = useT();
  const f = { accessToken: auth.user?.access_token };
  const qc = useQueryClient();

  const isAdmin = orgRole === "admin";

  const orgQ = useQuery({
    queryKey: ["org"],
    queryFn: () => api.getOrg(f),
  });
  const membersQ = useQuery({
    queryKey: ["org-members"],
    queryFn: () => api.listOrgMembers(f),
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

  // When resend lands a temp password, surface it through the same
  // callout the invite dialog uses — admin needs to read + copy + send
  // it before dismissing. magic_link mode just toasts.
  const [resendTempPassword, setResendTempPassword] = useState<{
    email: string;
    password: string;
  } | null>(null);

  const resendM = useMutation({
    mutationFn: (vars: { userId: string; email: string }) =>
      api.resendOrgInvite(f, vars.userId).then((r) => ({ result: r, email: vars.email })),
    onSuccess: ({ result, email: recipient }) => {
      if (result.delivery === "temporary_password" && result.temporary_password) {
        setResendTempPassword({
          email: recipient,
          password: result.temporary_password,
        });
        toast.success(t("invite.resendSuccessTempPassword"));
      } else {
        toast.success(t("invite.resendSuccessMagic"));
      }
    },
    onError: (e) => toast.error((e as Error).message || t("invite.resendFailed")),
  });

  const revokeM = useMutation({
    mutationFn: (userId: string) => api.revokeOrgInvite(f, userId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["org-members"] });
      toast.success(t("invite.revokeSuccess"));
    },
    onError: (e) => toast.error((e as Error).message || t("invite.revokeFailed")),
  });

  return (
    <div className="page-container">
      <PageHeader
        title={t("org.title")}
        description={t("org.description")}
        actions={isAdmin ? <InviteMemberDialog /> : undefined}
      />

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
                ? (m) =>
                    m.pending ? (
                      <PendingActions
                        m={m}
                        onResend={() =>
                          resendM.mutate({
                            userId: m.user.id,
                            email: m.user.email,
                          })
                        }
                        onRevoke={() => revokeM.mutate(m.user.id)}
                        busy={resendM.isPending || revokeM.isPending}
                      />
                    ) : (
                      <RemoveAction
                        name={m.user.display_name}
                        onConfirm={() => removeM.mutate(m.user.id)}
                        busy={removeM.isPending}
                      />
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
      </div>

      <Dialog
        open={resendTempPassword !== null}
        onOpenChange={(next) => {
          if (!next) setResendTempPassword(null);
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t("invite.tempPasswordTitle")}</DialogTitle>
          </DialogHeader>
          {resendTempPassword && (
            <TempPasswordCallout
              email={resendTempPassword.email}
              password={resendTempPassword.password}
              onDismiss={() => setResendTempPassword(null)}
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function RemoveAction({
  name,
  onConfirm,
  busy,
}: {
  name: string;
  onConfirm: () => void;
  busy: boolean;
}) {
  const { t } = useT();
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button
          size="sm"
          variant="ghost"
          disabled={busy}
          className="text-muted-foreground hover:text-destructive"
        >
          {t("common.remove")}
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>
            {t("org.removeMemberTitle", { name })}
          </AlertDialogTitle>
          <AlertDialogDescription>
            {t("org.removeMemberDesc")}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
          <AlertDialogAction
            className={buttonVariants({ variant: "destructive" })}
            onClick={onConfirm}
          >
            {t("common.remove")}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

function PendingActions({
  m,
  onResend,
  onRevoke,
  busy,
}: {
  m: MemberRow;
  onResend: () => void;
  onRevoke: () => void;
  busy: boolean;
}) {
  const { t } = useT();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          size="sm"
          variant="ghost"
          disabled={busy}
          className="size-8 p-0 text-muted-foreground"
          aria-label="Invite actions"
        >
          <MoreHorizontal className="size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-48">
        <DropdownMenuItem onSelect={onResend}>
          {t("invite.resend")}
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <DropdownMenuItem
              onSelect={(e) => e.preventDefault()}
              className="text-destructive focus:text-destructive"
            >
              {t("invite.revoke")}
            </DropdownMenuItem>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>{t("invite.revoke")}</AlertDialogTitle>
              <AlertDialogDescription>
                {t("invite.revokeConfirm", { email: m.user.email })}
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
              <AlertDialogAction
                className={buttonVariants({ variant: "destructive" })}
                onClick={onRevoke}
              >
                {t("invite.revoke")}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
