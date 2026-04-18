import { useEffect, useState } from "react";
import { useAuth } from "react-oidc-context";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, type Team } from "@/api";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
  const qc = useQueryClient();
  const f = { accessToken: auth.user?.access_token };

  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [sharing, setSharing] = useState(false);

  const noteQ = useQuery({
    queryKey: ["note", noteId],
    queryFn: () => api.getNote(f, noteId!),
    enabled: !!noteId,
  });

  useEffect(() => {
    if (noteQ.data) {
      setTitle(noteQ.data.title);
      setBody(noteQ.data.body);
    }
  }, [noteQ.data]);

  const updateM = useMutation({
    mutationFn: () => api.updateNote(f, noteId!, { title, body }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["notes"] });
      qc.invalidateQueries({ queryKey: ["note", noteId] });
    },
  });

  const deleteM = useMutation({
    mutationFn: () => api.deleteNote(f, noteId!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["notes"] });
      onClose();
    },
  });

  const teamName = teams.find((t) => t.id === noteQ.data?.team_id)?.name;

  return (
    <>
      <Dialog open={!!noteId} onOpenChange={(open) => !open && onClose()}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Note</DialogTitle>
          </DialogHeader>

          {noteQ.isLoading && <p className="text-muted-foreground">Loading…</p>}
          {noteQ.error && (
            <p className="text-destructive text-sm">
              {(noteQ.error as Error).message}
            </p>
          )}

          {noteQ.data && (
            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="detail-title">Title</Label>
                <Input
                  id="detail-title"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="detail-body">Body</Label>
                <Textarea
                  id="detail-body"
                  rows={10}
                  value={body}
                  onChange={(e) => setBody(e.target.value)}
                />
              </div>
              <div className="text-xs text-muted-foreground">
                {teamName ? `Team: ${teamName}` : "Personal note"}
                {" · "}
                Updated {new Date(noteQ.data.updated_at).toLocaleString()}
              </div>
              {(updateM.error || deleteM.error) && (
                <p className="text-sm text-destructive">
                  {((updateM.error ?? deleteM.error) as Error).message}
                </p>
              )}
            </div>
          )}

          <DialogFooter className="justify-between sm:justify-between">
            <div className="flex gap-2">
              <Button
                variant="destructive"
                onClick={() => deleteM.mutate()}
                disabled={!noteId || deleteM.isPending}
              >
                {deleteM.isPending ? "Deleting…" : "Delete"}
              </Button>
              <Button
                variant="outline"
                onClick={() => setSharing(true)}
                disabled={!noteId}
              >
                Share
              </Button>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" onClick={onClose}>
                Close
              </Button>
              <Button
                onClick={() => updateM.mutate()}
                disabled={
                  !noteId ||
                  updateM.isPending ||
                  (title === noteQ.data?.title && body === noteQ.data?.body)
                }
              >
                {updateM.isPending ? "Saving…" : "Save"}
              </Button>
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ShareDialog
        noteId={sharing ? noteId : null}
        noteTitle={noteQ.data?.title ?? ""}
        teams={teams}
        onClose={() => setSharing(false)}
      />
    </>
  );
}
