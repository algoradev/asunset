import { useState } from "react";
import { useAuth } from "react-oidc-context";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api, type Team } from "@/api";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

export function NewNoteDialog({ teams }: { teams: Team[] }) {
  const auth = useAuth();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [teamId, setTeamId] = useState<string>("");

  const mutation = useMutation({
    mutationFn: () =>
      api.createNote(
        { accessToken: auth.user?.access_token },
        { title: title.trim(), body, team_id: teamId || null },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["notes"] });
      setOpen(false);
      setTitle("");
      setBody("");
      setTeamId("");
    },
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>New note</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New note</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="note-title">Title</Label>
            <Input
              id="note-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              autoFocus
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="note-body">Body</Label>
            <Textarea
              id="note-body"
              rows={6}
              value={body}
              onChange={(e) => setBody(e.target.value)}
            />
          </div>
          {teams.length > 0 && (
            <div className="space-y-2">
              <Label htmlFor="note-team">Team (optional)</Label>
              <select
                id="note-team"
                className="w-full rounded-md border border-input bg-background h-10 px-2 text-sm"
                value={teamId}
                onChange={(e) => setTeamId(e.target.value)}
              >
                <option value="">— personal —</option>
                {teams.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
            </div>
          )}
          {mutation.error && (
            <p className="text-sm text-destructive">
              {(mutation.error as Error).message}
            </p>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button
            onClick={() => mutation.mutate()}
            disabled={title.trim().length === 0 || mutation.isPending}
          >
            {mutation.isPending ? "Creating…" : "Create"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
