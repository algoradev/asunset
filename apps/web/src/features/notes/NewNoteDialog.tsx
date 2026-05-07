import { useState } from "react";
import { useAuth } from "react-oidc-context";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, Plus } from "lucide-react";
import { toast } from "sonner";

import { api, type Team } from "@/api";
import { RESOURCE } from "@/config/resource";
import { useT } from "@/lib/useT";
import { Button } from "@/components/ui/button";
import {
  Field,
  FieldDescription,
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
import { Spinner } from "@/components/ui/spinner";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

const PERSONAL = "__personal__";

export function NewNoteDialog({ teams }: { teams: Team[] }) {
  const auth = useAuth();
  const qc = useQueryClient();
  const { t } = useT();
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [teamId, setTeamId] = useState<string>(PERSONAL);

  const mutation = useMutation({
    mutationFn: () =>
      api.createNote(
        { accessToken: auth.user?.access_token },
        {
          title: title.trim(),
          body,
          team_id: teamId === PERSONAL ? null : teamId,
        },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["notes"] });
      setOpen(false);
      setTitle("");
      setBody("");
      setTeamId(PERSONAL);
      toast.success(t("notes.created", { resource: RESOURCE.name }));
    },
    onError: (e) => toast.error((e as Error).message),
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Plus className="size-4" />
          {t("notes.new")}
          <ChevronRight className="ml-1 opacity-70" />
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("notes.new")}</DialogTitle>
        </DialogHeader>
        <FieldGroup>
          <Field>
            <FieldLabel htmlFor="note-title">{t("notes.title")}</FieldLabel>
            <Input
              id="note-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={t("notes.titlePlaceholder", { resource: RESOURCE.name })}
              autoFocus
            />
          </Field>
          <Field>
            <FieldLabel htmlFor="note-body">{t("notes.body")}</FieldLabel>
            <Textarea
              id="note-body"
              rows={6}
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder={t("notes.bodyPlaceholder")}
            />
          </Field>
          {teams.length > 0 && (
            <Field>
              <FieldLabel htmlFor="note-team">{t("notes.team")}</FieldLabel>
              <Select value={teamId} onValueChange={setTeamId}>
                <SelectTrigger id="note-team">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={PERSONAL}>{t("common.personal")}</SelectItem>
                  {teams.map((tm) => (
                    <SelectItem key={tm.id} value={tm.id}>
                      {tm.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FieldDescription>
                {t("notes.teamAssignHint", { resource: RESOURCE.name.toLowerCase() })}
              </FieldDescription>
            </Field>
          )}
        </FieldGroup>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            {t("common.cancel")}
          </Button>
          <Button
            onClick={() => mutation.mutate()}
            disabled={title.trim().length === 0 || mutation.isPending}
          >
            {mutation.isPending && <Spinner className="size-4" />}
            {mutation.isPending ? t("common.creating") : t("common.create")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
