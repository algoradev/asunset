import { useState } from "react";
import { useAuth } from "react-oidc-context";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Building2, Share2, Trash2, User2, Users2, X } from "lucide-react";

import {
  api,
  type Note,
  type NoteGrant,
  type ShareBody,
  type Team,
} from "@/api";
import { RESOURCE } from "@/config/resource";
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
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Field,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { ErrorState } from "@/components/States";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ShareDialog } from "./ShareDialog";

export function NoteDetailDialog({
  noteId,
  onClose,
  teams,
}: {
  noteId: string | null;
  onClose: () => void;
  teams: Team[];
}) {
  const auth = useAuth();
  const f = { accessToken: auth.user?.access_token };

  const noteQ = useQuery({
    queryKey: ["note", noteId],
    queryFn: () => api.getNote(f, noteId!),
    enabled: !!noteId,
  });

  return (
    <Dialog open={!!noteId} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{RESOURCE.name}</DialogTitle>
        </DialogHeader>

        {noteQ.isLoading && <DetailSkeleton />}
        {noteQ.error && <ErrorState error={noteQ.error} />}
        {noteQ.data && (
          // key={note.id} remounts the editor when the dialog switches
          // between different notes, so useState initializers re-run
          // with the new note's data — no Effect needed to sync.
          <NoteEditor
            key={noteQ.data.id}
            note={noteQ.data}
            teams={teams}
            onClose={onClose}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function NoteEditor({
  note,
  teams,
  onClose,
}: {
  note: Note;
  teams: Team[];
  onClose: () => void;
}) {
  const auth = useAuth();
  const qc = useQueryClient();
  const { t } = useT();
  const f = { accessToken: auth.user?.access_token };

  const [title, setTitle] = useState(note.title);
  const [body, setBody] = useState(note.body);
  const [sharing, setSharing] = useState(false);

  const updateM = useMutation({
    mutationFn: () => api.updateNote(f, note.id, { title, body }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["notes"] });
      qc.invalidateQueries({ queryKey: ["note", note.id] });
      toast.success(t("notes.saved", { resource: RESOURCE.name }));
    },
    onError: (e) => toast.error((e as Error).message),
  });

  const deleteM = useMutation({
    mutationFn: () => api.deleteNote(f, note.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["notes"] });
      onClose();
      toast.success(t("notes.deleted", { resource: RESOURCE.name }));
    },
    onError: (e) => toast.error((e as Error).message),
  });

  // Shares are gated on `can_delete` server-side. Non-owners get 404 and
  // `retry: false` in the query client keeps that from rerunning; we
  // simply hide the panel when the query doesn't succeed.
  const sharesQ = useQuery({
    queryKey: ["note-shares", note.id],
    queryFn: () => api.listNoteShares(f, note.id),
  });

  const removeShareM = useMutation({
    mutationFn: (grant: NoteGrant) =>
      api.unshareNote(f, note.id, grantToShareBody(grant)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["note-shares", note.id] });
      toast.success(t("notes.shareRemoved"));
    },
    onError: (e) => toast.error((e as Error).message),
  });

  const teamName = teams.find((team) => team.id === note.team_id)?.name;
  const dirty = title !== note.title || body !== note.body;

  return (
    <>
      <div className="flex flex-col gap-5">
        <FieldGroup>
          <Field>
            <FieldLabel htmlFor="detail-title">{t("notes.title")}</FieldLabel>
            <Input
              id="detail-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </Field>
          <Field>
            <FieldLabel htmlFor="detail-body">{t("notes.body")}</FieldLabel>
            <Textarea
              id="detail-body"
              rows={10}
              value={body}
              onChange={(e) => setBody(e.target.value)}
            />
          </Field>
        </FieldGroup>

        <div className="flex flex-wrap items-center gap-2 text-caption">
          <Badge variant="soft" size="sm">
            {teamName ?? t("common.personal")}
          </Badge>
          <span>
            {t("notes.detailUpdated", {
              when: new Date(note.updated_at).toLocaleString(),
            })}
          </span>
        </div>

        {sharesQ.data && (
          <>
            <Separator />
            <SharesPanel
              grants={sharesQ.data}
              onRemove={(g) => removeShareM.mutate(g)}
              removing={removeShareM.isPending}
              t={t}
            />
          </>
        )}
      </div>

      <DialogFooter className="flex-col-reverse gap-2 sm:flex-row sm:justify-between">
        <div className="flex gap-2">
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button
                variant="outline"
                className="text-destructive hover:text-destructive"
                disabled={deleteM.isPending}
              >
                {deleteM.isPending ? (
                  <Spinner className="size-4" />
                ) : (
                  <Trash2 className="size-4" />
                )}
                {t("common.delete")}
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>
                  {t("notes.deletePrompt", {
                    resource: RESOURCE.name.toLowerCase(),
                  })}
                </AlertDialogTitle>
                <AlertDialogDescription>
                  {t("notes.deleteDesc", { title: note.title })}
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
                <AlertDialogAction
                  className={buttonVariants({ variant: "destructive" })}
                  onClick={() => deleteM.mutate()}
                >
                  {t("common.delete")}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
          <Button variant="outline" onClick={() => setSharing(true)}>
            <Share2 className="size-4" />
            {t("common.share")}
          </Button>
        </div>
        <div className="flex gap-2 sm:justify-end">
          <Button variant="ghost" onClick={onClose}>
            {t("common.close")}
          </Button>
          <Button
            onClick={() => updateM.mutate()}
            disabled={!dirty || updateM.isPending}
          >
            {updateM.isPending && <Spinner className="size-4" />}
            {updateM.isPending ? t("common.saving") : t("common.save")}
          </Button>
        </div>
      </DialogFooter>

      <ShareDialog
        noteId={sharing ? note.id : null}
        noteTitle={note.title}
        teams={teams}
        onClose={() => setSharing(false)}
      />
    </>
  );
}

function DetailSkeleton() {
  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Skeleton className="h-4 w-12" />
        <Skeleton className="h-10 w-full" />
      </div>
      <div className="space-y-2">
        <Skeleton className="h-4 w-12" />
        <Skeleton className="h-40 w-full" />
      </div>
      <Skeleton className="h-3 w-64" />
    </div>
  );
}

function SharesPanel({
  grants,
  onRemove,
  removing,
  t,
}: {
  grants: NoteGrant[];
  onRemove: (g: NoteGrant) => void;
  removing: boolean;
  t: (k: string, opts?: Record<string, unknown>) => string;
}) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="text-section-title">{t("notes.sharedWith")}</div>
        <span className="text-caption">
          {t("common.entry", { count: grants.length })}
        </span>
      </div>
      {grants.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          {t("notes.notSharedYet")}
        </p>
      ) : (
        <ul className="divide-y rounded-md border">
          {grants.map((g, i) => (
            <li
              key={`${g.kind}-${g.user_id ?? g.team_id ?? g.org_id}-${i}`}
              className="flex items-center gap-3 px-3 py-2"
            >
              <GrantIcon kind={g.kind} />
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-medium">
                  {grantLabel(g)}
                </div>
                {g.email && (
                  <div className="truncate text-xs text-muted-foreground">
                    {g.email}
                  </div>
                )}
              </div>
              <Badge variant="soft" size="sm">
                {g.relation === "viewer" ? t("common.viewer") : t("common.editor")}
              </Badge>
              <Button
                size="icon"
                variant="ghost"
                onClick={() => onRemove(g)}
                disabled={removing}
                aria-label={t("common.remove")}
                className="size-8"
              >
                <X className="size-4" />
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function GrantIcon({ kind }: { kind: NoteGrant["kind"] }) {
  const Icon = kind === "user" ? User2 : kind === "team" ? Users2 : Building2;
  return <Icon className="size-4 shrink-0 text-muted-foreground" />;
}

function grantLabel(g: NoteGrant): string {
  if (g.kind === "user") return g.label || g.email || "Unknown user";
  if (g.kind === "team") return g.label ? `Team · ${g.label}` : "Unknown team";
  return g.label ? `Everyone in ${g.label}` : "Whole organization";
}

function grantToShareBody(g: NoteGrant): ShareBody {
  if (g.kind === "user") return { user_id: g.user_id!, relation: g.relation };
  if (g.kind === "team") return { team_id: g.team_id!, relation: g.relation };
  return { org: true, relation: g.relation };
}
