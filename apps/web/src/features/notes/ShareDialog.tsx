import { useState } from "react";
import { useAuth } from "react-oidc-context";
import { useMutation } from "@tanstack/react-query";

import { api, type Relation, type ShareBody, type Team } from "@/api";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";

type Target = "user" | "team" | "org";

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
  const f = { accessToken: auth.user?.access_token };

  const [target, setTarget] = useState<Target>("user");
  const [relation, setRelation] = useState<Relation>("viewer");
  const [email, setEmail] = useState("");
  const [teamId, setTeamId] = useState<string>(teams[0]?.id ?? "");
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

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
            ? teams.find((t) => t.id === body.team_id)?.name ?? "team"
            : "organization";
      setStatusMsg(`Shared with ${targetDesc} as ${body.relation}.`);
      setEmail("");
    },
  });

  return (
    <Dialog
      open={!!noteId}
      onOpenChange={(open) => {
        if (!open) {
          onClose();
          setStatusMsg(null);
        }
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Share &quot;{noteTitle}&quot;</DialogTitle>
          <DialogDescription>
            Grant access to a user, a team, or the whole organization.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label>Target</Label>
            <RadioGroup
              value={target}
              onValueChange={(v) => setTarget(v as Target)}
              className="flex gap-6"
            >
              <RadioLabel value="user" id="tg-user" label="User" />
              <RadioLabel value="team" id="tg-team" label="Team" />
              <RadioLabel value="org" id="tg-org" label="Whole org" />
            </RadioGroup>
          </div>

          {target === "user" && (
            <div className="space-y-2">
              <Label htmlFor="share-email">Email</Label>
              <Input
                id="share-email"
                type="email"
                placeholder="bob@asunset.local"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                Resolved via Keycloak — they don't need to have logged in yet.
              </p>
            </div>
          )}

          {target === "team" && (
            <div className="space-y-2">
              <Label htmlFor="share-team">Team</Label>
              <select
                id="share-team"
                className="w-full rounded-md border border-input bg-background h-10 px-2 text-sm"
                value={teamId}
                onChange={(e) => setTeamId(e.target.value)}
              >
                {teams.length === 0 && <option value="">(no teams)</option>}
                {teams.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="space-y-2">
            <Label>Permission</Label>
            <RadioGroup
              value={relation}
              onValueChange={(v) => setRelation(v as Relation)}
              className="flex gap-6"
            >
              <RadioLabel value="viewer" id="rel-viewer" label="Viewer" />
              <RadioLabel value="editor" id="rel-editor" label="Editor" />
            </RadioGroup>
          </div>

          {statusMsg && <p className="text-sm text-green-600">{statusMsg}</p>}
          {mutation.error && (
            <p className="text-sm text-destructive">
              {(mutation.error as Error).message}
            </p>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Close
          </Button>
          <Button
            onClick={() => mutation.mutate()}
            disabled={
              mutation.isPending ||
              (target === "user" && email.trim().length === 0) ||
              (target === "team" && !teamId)
            }
          >
            {mutation.isPending ? "Sharing…" : "Share"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function RadioLabel({
  value,
  id,
  label,
}: {
  value: string;
  id: string;
  label: string;
}) {
  return (
    <div className="flex items-center gap-2">
      <RadioGroupItem value={value} id={id} />
      <Label htmlFor={id}>{label}</Label>
    </div>
  );
}
