import { useState } from "react";
import { useAuth } from "react-oidc-context";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Building2, Share2, User2, Users2 } from "lucide-react";
import { toast } from "sonner";

import { api, type Relation, type ShareBody, type Team } from "@/api";
import { UserCombobox } from "@/components/UserCombobox";
import { useT } from "@/lib/useT";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Field,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";

type Target = "user" | "team" | "org";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function ShareDialog({
  noteId,
  noteTitle,
  teams,
  onClose,
}: {
  noteId: string | null;
  noteTitle: string;
  teams: Team[];
  onClose: () => void;
}) {
  const auth = useAuth();
  const qc = useQueryClient();
  const { t } = useT();
  const f = { accessToken: auth.user?.access_token };

  const [target, setTarget] = useState<Target>("user");
  const [relation, setRelation] = useState<Relation>("viewer");
  const [email, setEmail] = useState("");
  const [teamId, setTeamId] = useState<string>(teams[0]?.id ?? "");

  const mutation = useMutation({
    mutationFn: async (): Promise<ShareBody> => {
      if (!noteId) throw new Error("no note");
      let body: ShareBody;
      if (target === "user") {
        const user = await api.lookupUser(f, email.trim());
        body = { user_id: user.id, relation };
      } else if (target === "team") {
        if (!teamId) throw new Error("pick a team");
        body = { team_id: teamId, relation };
      } else {
        body = { org: true, relation };
      }
      await api.shareNote(f, noteId, body);
      return body;
    },
    onSuccess: (body) => {
      const targetDesc =
        "user_id" in body
          ? email
          : "team_id" in body
            ? teams.find((x) => x.id === body.team_id)?.name ?? "team"
            : "organization";
      toast.success(
        t("notes.shareSuccess", {
          target: targetDesc,
          relation: relationLabel(body.relation, t),
        }),
      );
      setEmail("");
      qc.invalidateQueries({ queryKey: ["note-shares", noteId] });
    },
    onError: (e) => toast.error((e as Error).message),
  });

  const emailValid = target !== "user" || EMAIL_RE.test(email.trim());
  const disabled =
    mutation.isPending ||
    (target === "user" && !emailValid) ||
    (target === "team" && !teamId);

  return (
    <Dialog
      open={!!noteId}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {t("notes.shareTitle", { title: noteTitle })}
          </DialogTitle>
          <DialogDescription>{t("notes.shareDesc")}</DialogDescription>
        </DialogHeader>

        <FieldGroup>
          <Field>
            <FieldLabel>{t("notes.shareTargetLabel")}</FieldLabel>
            <ToggleGroup
              type="single"
              value={target}
              onValueChange={(v) => v && setTarget(v as Target)}
              className="grid grid-cols-3 gap-2"
            >
              <ToggleGroupItem
                value="user"
                className="justify-center gap-2 data-[state=on]:bg-accent"
              >
                <User2 className="size-4" /> {t("notes.shareTargetUser")}
              </ToggleGroupItem>
              <ToggleGroupItem
                value="team"
                className="justify-center gap-2 data-[state=on]:bg-accent"
                disabled={teams.length === 0}
              >
                <Users2 className="size-4" /> {t("notes.shareTargetTeam")}
              </ToggleGroupItem>
              <ToggleGroupItem
                value="org"
                className="justify-center gap-2 data-[state=on]:bg-accent"
              >
                <Building2 className="size-4" /> {t("notes.shareTargetOrg")}
              </ToggleGroupItem>
            </ToggleGroup>
          </Field>

          {target === "user" && (
            <Field>
              <FieldLabel htmlFor="share-email">
                {t("notes.shareRecipient")}
              </FieldLabel>
              <UserCombobox value={email} onChange={setEmail} />
              <p className="text-caption">{t("notes.shareRecipientHint")}</p>
            </Field>
          )}

          {target === "team" && (
            <Field>
              <FieldLabel htmlFor="share-team">{t("notes.team")}</FieldLabel>
              <Select value={teamId} onValueChange={setTeamId}>
                <SelectTrigger id="share-team">
                  <SelectValue placeholder={t("notes.teamPickerPlaceholder")} />
                </SelectTrigger>
                <SelectContent>
                  {teams.map((tm) => (
                    <SelectItem key={tm.id} value={tm.id}>
                      {tm.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
          )}

          {target === "org" && (
            <div className="rounded-md border bg-muted/40 p-3 text-sm text-muted-foreground flex items-start gap-2">
              <Share2 className="mt-0.5 size-4 shrink-0" />
              <span>
                {t("notes.shareOrgInfo", {
                  relation: relationLabel(relation, t),
                })}
              </span>
            </div>
          )}

          <Field>
            <FieldLabel>{t("notes.sharePermission")}</FieldLabel>
            <ToggleGroup
              type="single"
              value={relation}
              onValueChange={(v) => v && setRelation(v as Relation)}
              className="grid grid-cols-2 gap-2"
            >
              <ToggleGroupItem
                value="viewer"
                className="justify-center data-[state=on]:bg-accent"
              >
                {t("common.viewer")}
              </ToggleGroupItem>
              <ToggleGroupItem
                value="editor"
                className="justify-center data-[state=on]:bg-accent"
              >
                {t("common.editor")}
              </ToggleGroupItem>
            </ToggleGroup>
          </Field>
        </FieldGroup>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {t("common.close")}
          </Button>
          <Button onClick={() => mutation.mutate()} disabled={disabled}>
            {mutation.isPending && <Spinner className="size-4" />}
            {mutation.isPending ? t("common.sharing") : t("common.share")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function relationLabel(r: Relation, t: (k: string) => string): string {
  return r === "viewer" ? t("common.viewer") : t("common.editor");
}
