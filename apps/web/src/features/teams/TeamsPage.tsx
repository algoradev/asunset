import { useState } from "react";
import { ChevronDown, ChevronRight, Plus, Trash2, Users } from "lucide-react";
import { toast } from "sonner";

import { type Role, type Team } from "@/api";
import {
  useAddTeamMember,
  useCreateTeam,
  useDeleteTeam,
  useRemoveTeamMember,
  useTeamMembers,
  useTeams,
  useUpdateTeamMemberRole,
} from "@/lib/platformHooks";
import { AddMemberRow } from "@/components/AddMemberRow";
import { MemberTable } from "@/components/MemberTable";
import { PageHeader } from "@/components/PageHeader";
import { TypedConfirmDialog } from "@/components/TypedConfirmDialog";
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
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import {
  Field,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/States";
import { Spinner } from "@/components/ui/spinner";

export function TeamsPage({ orgRole }: { orgRole: Role }) {
  const { t } = useT();

  const isOrgAdmin = orgRole === "admin";
  const [createOpen, setCreateOpen] = useState(false);

  const teamsQ = useTeams();

  const deleteM = useDeleteTeam({
    onSuccess: () => toast.success(t("teams.deletedToast")),
    onError: (e) => toast.error(e.message),
  });

  return (
    <div className="page-container">
      <PageHeader
        title={t("teams.title")}
        description={t("teams.description")}
        actions={
          isOrgAdmin ? (
            <CreateTeamDialog open={createOpen} onOpenChange={setCreateOpen} />
          ) : null
        }
      />

      {teamsQ.isLoading && <TeamListSkeleton />}
      {teamsQ.error && (
        <ErrorState error={teamsQ.error} onRetry={() => teamsQ.refetch()} />
      )}
      {teamsQ.data?.length === 0 && (
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <Users />
            </EmptyMedia>
            <EmptyTitle>{t("teams.emptyTitle")}</EmptyTitle>
            <EmptyDescription>
              {isOrgAdmin
                ? t("teams.emptyDescAdmin")
                : t("teams.emptyDescMember")}
            </EmptyDescription>
          </EmptyHeader>
          {isOrgAdmin && (
            <EmptyContent>
              <Button onClick={() => setCreateOpen(true)}>
                <Plus className="size-4" /> {t("teams.new")}
              </Button>
            </EmptyContent>
          )}
        </Empty>
      )}

      {teamsQ.data && teamsQ.data.length > 0 && (
        <div className="rounded-lg border bg-card divide-y">
          {teamsQ.data.map((team) => (
            <TeamRow
              key={team.id}
              team={team}
              isOrgAdmin={isOrgAdmin}
              onDelete={() => deleteM.mutate({ teamId: team.id })}
              deleting={deleteM.isPending}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function CreateTeamDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { t } = useT();
  const [name, setName] = useState("");

  const createM = useCreateTeam({
    onSuccess: () => {
      setName("");
      onOpenChange(false);
      toast.success(t("teams.createdToast"));
    },
    onError: (e) => toast.error(e.message),
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button>
          <Plus className="size-4" /> {t("teams.new")}
          <ChevronRight className="ml-1 opacity-70" />
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("teams.create")}</DialogTitle>
        </DialogHeader>
        <FieldGroup>
          <Field>
            <FieldLabel htmlFor="new-team">{t("teams.name")}</FieldLabel>
            <Input
              id="new-team"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("teams.namePlaceholder")}
              autoFocus
            />
          </Field>
        </FieldGroup>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button
            onClick={() => createM.mutate({ name: name.trim() })}
            disabled={name.trim().length === 0 || createM.isPending}
          >
            {createM.isPending && <Spinner className="size-4" />}
            {createM.isPending ? t("common.creating") : t("common.create")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function TeamListSkeleton() {
  return (
    <div className="rounded-lg border bg-card divide-y">
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="flex items-center gap-3 px-4 py-3">
          <Skeleton className="size-4" />
          <Skeleton className="h-4 w-48" />
        </div>
      ))}
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
  const { t } = useT();
  const [open, setOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  return (
    <>
      <Collapsible open={open} onOpenChange={setOpen}>
        <div className="flex items-center justify-between gap-2 px-4 py-3">
          <CollapsibleTrigger asChild>
            <button className="flex flex-1 items-center gap-3 text-left">
              <ChevronDown
                className={`size-4 text-muted-foreground transition-transform ${
                  open ? "rotate-0" : "-rotate-90"
                }`}
              />
              <span className="text-sm font-medium">{team.name}</span>
            </button>
          </CollapsibleTrigger>
          {isOrgAdmin && (
            <Button
              size="icon"
              variant="ghost"
              disabled={deleting}
              aria-label={t("common.delete")}
              className="size-8 text-muted-foreground hover:text-destructive"
              onClick={() => setConfirmOpen(true)}
            >
              <Trash2 className="size-4" />
            </Button>
          )}
        </div>
        <CollapsibleContent>
          <div className="border-t bg-muted/30 p-4">
            <TeamMembersPanel team={team} canManage={isOrgAdmin} />
          </div>
        </CollapsibleContent>
      </Collapsible>

      <TypedConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={t("teams.deleteTitle", { name: team.name })}
        description={t("teams.deleteDesc")}
        confirmPhrase={team.name}
        actionLabel={t("teams.deleteAction")}
        busy={deleting}
        onConfirm={() => {
          onDelete();
          setConfirmOpen(false);
        }}
      />
    </>
  );
}

function TeamMembersPanel({
  team,
  canManage,
}: {
  team: Team;
  canManage: boolean;
}) {
  const { t } = useT();

  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("member");

  const membersQ = useTeamMembers(team.id);

  // The lookup→add composite lives in the SDK hook; the invalidation
  // scope (this team only) does too.
  const addM = useAddTeamMember({
    onSuccess: () => {
      setEmail("");
      toast.success(t("teams.memberAdded"));
    },
    onError: (e) => toast.error(e.message),
  });

  const updateRoleM = useUpdateTeamMemberRole({
    onSuccess: (_data, vars) =>
      toast.success(t("teams.roleUpdated", { role: vars.newRole })),
    onError: (e) => toast.error(e.message),
  });

  const removeM = useRemoveTeamMember({
    onSuccess: () => toast.success(t("teams.memberRemoved")),
    onError: (e) => toast.error(e.message),
  });

  return (
    <div className="flex flex-col gap-4">
      {membersQ.isLoading && (
        <div className="rounded-lg border bg-card p-3 space-y-2">
          {Array.from({ length: 2 }).map((_, i) => (
            <div key={i} className="flex items-center gap-3">
              <Skeleton className="size-7 rounded-full" />
              <Skeleton className="h-4 w-32" />
            </div>
          ))}
        </div>
      )}
      {membersQ.data && membersQ.data.length === 0 && (
        <p className="text-sm text-muted-foreground">
          {t("teams.noMembersYet")}
        </p>
      )}
      {membersQ.data && membersQ.data.length > 0 && (
        <MemberTable
          rows={membersQ.data}
          showJoined={false}
          onRoleChange={
            canManage
              ? (userId, newRole) =>
                  updateRoleM.mutate({ teamId: team.id, userId, newRole })
              : undefined
          }
          roleBusy={
            updateRoleM.isPending
              ? (updateRoleM.variables?.userId ?? null)
              : null
          }
          actions={
            canManage
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
                          {t("teams.removeMemberTitle", {
                            name: m.user.display_name,
                          })}
                        </AlertDialogTitle>
                        <AlertDialogDescription>
                          {t("teams.removeMemberDesc")}
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>
                          {t("common.cancel")}
                        </AlertDialogCancel>
                        <AlertDialogAction
                          className={buttonVariants({ variant: "destructive" })}
                          onClick={() => removeM.mutate({ teamId: team.id, userId: m.user.id })}
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
      {canManage && (
        <AddMemberRow
          inputId={`add-${team.id}`}
          roleId={`role-${team.id}`}
          email={email}
          onEmailChange={setEmail}
          role={role}
          onRoleChange={setRole}
          onSubmit={() => addM.mutate({ teamId: team.id, email: email.trim(), role })}
          busy={addM.isPending}
        />
      )}
    </div>
  );
}
