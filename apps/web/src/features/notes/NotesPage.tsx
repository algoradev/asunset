import { useEffect, useState } from "react";
import { useAuth } from "react-oidc-context";
import { useQuery } from "@tanstack/react-query";

import { api, type Note, type NoteScope } from "@/api";
import { cn } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { NewNoteDialog } from "./NewNoteDialog";
import { NoteDetailDialog } from "./NoteDetailDialog";

const TABS: { scope: NoteScope; label: string }[] = [
  { scope: "mine", label: "Mine" },
  { scope: "team", label: "My teams" },
  { scope: "shared", label: "Shared with me" },
  { scope: "org", label: "Organization" },
];

export function NotesPage() {
  const auth = useAuth();
  const token = auth.user?.access_token;
  const f = { accessToken: token };

  const [scope, setScope] = useState<NoteScope>("mine");
  const [selectedTeam, setSelectedTeam] = useState<string | null>(null);
  const [openNote, setOpenNote] = useState<Note | null>(null);

  const teamsQ = useQuery({
    queryKey: ["teams"],
    queryFn: () => api.listTeams(f),
    enabled: !!token,
  });

  // Default to first team when switching into "team" scope.
  useEffect(() => {
    if (scope === "team" && !selectedTeam && teamsQ.data?.length) {
      setSelectedTeam(teamsQ.data[0].id);
    }
  }, [scope, selectedTeam, teamsQ.data]);

  const notesEnabled =
    !!token && (scope !== "team" || !!selectedTeam);

  const notesQ = useQuery({
    queryKey: ["notes", scope, scope === "team" ? selectedTeam : null],
    queryFn: () =>
      scope === "team"
        ? api.listNotes(f, "team", selectedTeam!)
        : api.listNotes(f, scope),
    enabled: notesEnabled,
  });

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Notes</h1>
        <NewNoteDialog teams={teamsQ.data ?? []} />
      </div>

      <div className="flex items-center gap-2 border-b">
        {TABS.map((t) => (
          <button
            key={t.scope}
            onClick={() => {
              setScope(t.scope);
              if (t.scope !== "team") setSelectedTeam(null);
            }}
            className={cn(
              "px-4 py-2 text-sm border-b-2 -mb-px transition-colors",
              scope === t.scope
                ? "border-primary text-foreground font-medium"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {scope === "team" && (
        <div className="flex items-center gap-2">
          <label className="text-sm text-muted-foreground">Team</label>
          <select
            className="rounded-md border border-input bg-background h-9 px-2 text-sm"
            value={selectedTeam ?? ""}
            onChange={(e) => setSelectedTeam(e.target.value || null)}
          >
            <option value="">— pick a team —</option>
            {teamsQ.data?.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
          {teamsQ.data?.length === 0 && (
            <span className="text-sm text-muted-foreground">
              You're not on any team yet.
            </span>
          )}
        </div>
      )}

      {notesQ.isLoading && notesEnabled && (
        <p className="text-muted-foreground">Loading notes…</p>
      )}
      {notesQ.error && (
        <p className="text-destructive text-sm">
          {(notesQ.error as Error).message}
        </p>
      )}
      {notesQ.data && notesQ.data.length === 0 && (
        <p className="text-muted-foreground">No notes in this view.</p>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {notesQ.data?.map((note) => (
          <Card
            key={note.id}
            className="cursor-pointer hover:shadow-md transition-shadow"
            onClick={() => setOpenNote(note)}
          >
            <CardHeader>
              <CardTitle className="text-base">{note.title}</CardTitle>
              {note.access_path && (
                <AccessBadge path={note.access_path} />
              )}
            </CardHeader>
            <CardContent>
              <p className="whitespace-pre-wrap text-sm text-muted-foreground line-clamp-4">
                {note.body || <em>(empty)</em>}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>

      <NoteDetailDialog
        noteId={openNote?.id ?? null}
        onClose={() => setOpenNote(null)}
        teams={teamsQ.data ?? []}
      />
    </div>
  );
}

function AccessBadge({ path }: { path: string }) {
  // Lightweight visual cue so users can see at a glance why a note is
  // on screen. Classes track the access_path naming convention.
  const kind = path === "owner"
    ? { label: "owner", cls: "bg-primary text-primary-foreground" }
    : path.startsWith("direct")
      ? { label: path.replace("direct:", "shared as "), cls: "bg-blue-100 text-blue-900" }
      : path.startsWith("team")
        ? { label: path, cls: "bg-emerald-100 text-emerald-900" }
        : path.startsWith("organization")
          ? { label: path, cls: "bg-amber-100 text-amber-900" }
          : { label: path, cls: "bg-muted text-muted-foreground" };
  return (
    <span
      className={`inline-flex items-center text-[10px] font-medium rounded-full px-2 py-0.5 w-fit ${kind.cls}`}
    >
      {kind.label}
    </span>
  );
}
