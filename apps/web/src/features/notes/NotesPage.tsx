import { useState } from "react";
import { useFetcher } from "@asunset/web-sdk";
import { useQuery } from "@tanstack/react-query";
import { Trans } from "react-i18next";
import { Download, LayoutGrid, Rows3 } from "lucide-react";

import { api, type Note, type NoteScope, type Team } from "@/api";
import { RESOURCE } from "@/config/resource";
import { AccessBadge } from "@/components/AccessBadge";
import { PageHeader } from "@/components/PageHeader";
import { useT } from "@/lib/useT";
import { useFeatures } from "@/lib/useFeatures";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { ErrorState } from "@/components/States";
import { NewNoteDialog } from "./NewNoteDialog";
import { NoteDetailDialog } from "./NoteDetailDialog";

type View = "table" | "grid";
type TFn = ReturnType<typeof useT>["t"];

export function NotesPage() {
  const { t } = useT();
  const f = useFetcher();
  const token = f.accessToken;
  const features = useFeatures();

  const [scope, setScope] = useState<NoteScope>("mine");
  const [selectedTeam, setSelectedTeam] = useState<string | null>(null);
  const [openNote, setOpenNote] = useState<Note | null>(null);
  const [view, setView] = useState<View>("table");
  const [exporting, setExporting] = useState(false);

  const TABS: { scope: NoteScope; label: string }[] = [
    { scope: "mine", label: t("notes.tabMine") },
    { scope: "team", label: t("notes.tabTeams") },
    { scope: "shared", label: t("notes.tabShared") },
    { scope: "org", label: t("notes.tabOrg") },
  ];

  const teamsQ = useQuery({
    queryKey: ["teams"],
    queryFn: () => api.listTeams(f),
    enabled: !!token,
  });

  // Derive the effective team id during render instead of syncing via
  // an Effect: when the user hasn't explicitly picked one, fall back to
  // the first available team. No state-sync, no extra render pass.
  const effectiveTeam =
    scope === "team"
      ? (selectedTeam ?? teamsQ.data?.[0]?.id ?? null)
      : null;

  const notesEnabled = !!token && (scope !== "team" || !!effectiveTeam);

  const notesQ = useQuery({
    queryKey: ["notes", scope, effectiveTeam],
    queryFn: () =>
      scope === "team"
        ? api.listNotes(f, "team", effectiveTeam!)
        : api.listNotes(f, scope),
    enabled: notesEnabled,
  });

  const teams = teamsQ.data ?? [];
  const teamById = new Map(teams.map((t) => [t.id, t.name]));
  const canExport = features.has("notes.export");

  async function handleExport() {
    if (!token || exporting) return;
    setExporting(true);
    try {
      const csv = await api.exportNotesCsv(f);
      const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = "notes.csv";
      document.body.append(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  }

  return (
    <>
      <div className="page-container">
        <PageHeader
          title={t("notes.plural")}
          description={scopeHint(scope, t)}
          actions={
            <>
              {canExport && (
                <Button
                  type="button"
                  variant="outline"
                  onClick={handleExport}
                  disabled={exporting}
                >
                  <Download className="size-4" />
                  {t("common.exportCsv")}
                </Button>
              )}
              <NewNoteDialog teams={teams} />
            </>
          }
        />

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-wrap items-center gap-3">
            <Tabs
              value={scope}
              onValueChange={(v) => {
                setScope(v as NoteScope);
                if (v !== "team") setSelectedTeam(null);
              }}
            >
              <TabsList>
                {TABS.map((tab) => (
                  <TabsTrigger key={tab.scope} value={tab.scope}>
                    {tab.label}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>

            {scope === "team" && (
              <TeamPicker
                teams={teams}
                value={effectiveTeam}
                onChange={setSelectedTeam}
              />
            )}
          </div>

          <ToggleGroup
            type="single"
            size="sm"
            value={view}
            onValueChange={(v) => v && setView(v as View)}
            className="self-start sm:self-auto"
          >
            <ToggleGroupItem value="table" aria-label={t("common.viewTable")}>
              <Rows3 className="size-4" />
            </ToggleGroupItem>
            <ToggleGroupItem value="grid" aria-label={t("common.viewGrid")}>
              <LayoutGrid className="size-4" />
            </ToggleGroupItem>
          </ToggleGroup>
        </div>

        <NotesBody
          view={view}
          notes={notesQ.data}
          loading={notesQ.isLoading && notesEnabled}
          error={notesQ.error}
          onRetry={() => notesQ.refetch()}
          onOpen={setOpenNote}
          scope={scope}
          teamById={teamById}
          t={t}
        />
      </div>

      <NoteDetailDialog
        noteId={openNote?.id ?? null}
        onClose={() => setOpenNote(null)}
        teams={teams}
      />
    </>
  );
}

function TeamPicker({
  teams,
  value,
  onChange,
}: {
  teams: Team[];
  value: string | null;
  onChange: (v: string | null) => void;
}) {
  const { t } = useT();
  if (teams.length === 0) {
    return (
      <span className="text-caption">{t("notes.teamPickerNone")}</span>
    );
  }
  return (
    <Select value={value ?? ""} onValueChange={(v) => onChange(v || null)}>
      <SelectTrigger className="h-9 w-56">
        <SelectValue placeholder={t("notes.teamPickerPlaceholder")} />
      </SelectTrigger>
      <SelectContent>
        {teams.map((team) => (
          <SelectItem key={team.id} value={team.id}>
            {team.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function NotesBody({
  view,
  notes,
  loading,
  error,
  onRetry,
  onOpen,
  scope,
  teamById,
  t,
}: {
  view: View;
  notes: Note[] | undefined;
  loading: boolean;
  error: unknown;
  onRetry: () => void;
  onOpen: (n: Note) => void;
  scope: NoteScope;
  teamById: Map<string, string>;
  t: TFn;
}) {
  if (loading) {
    return view === "table" ? <NoteTableSkeleton t={t} /> : <NoteGridSkeleton />;
  }
  if (error) return <ErrorState error={error} onRetry={onRetry} />;
  if (notes && notes.length === 0) {
    return (
      <Empty>
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <RESOURCE.icon />
          </EmptyMedia>
          <EmptyTitle>{t("notes.emptyTitle")}</EmptyTitle>
          <EmptyDescription>{scopeHint(scope, t)}</EmptyDescription>
        </EmptyHeader>
        {scope === "mine" && (
          <EmptyContent>
            <p className="text-caption">
              <Trans
                i18nKey="notes.emptyKbdHint"
                values={{ resource: RESOURCE.name.toLowerCase() }}
                components={{
                  kbd: (
                    <kbd className="rounded border bg-muted px-1.5 py-0.5 font-mono text-[11px]" />
                  ),
                }}
              />
            </p>
          </EmptyContent>
        )}
      </Empty>
    );
  }
  if (!notes) return null;

  return view === "table" ? (
    <NoteTable notes={notes} onOpen={onOpen} teamById={teamById} t={t} />
  ) : (
    <NoteGrid notes={notes} onOpen={onOpen} t={t} />
  );
}

function NoteTable({
  notes,
  onOpen,
  teamById,
  t,
}: {
  notes: Note[];
  onOpen: (n: Note) => void;
  teamById: Map<string, string>;
  t: TFn;
}) {
  return (
    <div className="rounded-lg border bg-card">
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="h-10 w-[40%]">{t("notes.columnTitle")}</TableHead>
            <TableHead className="h-10">{t("notes.columnScope")}</TableHead>
            <TableHead className="h-10">{t("notes.columnAccess")}</TableHead>
            <TableHead className="h-10 text-right">
              {t("notes.columnUpdated")}
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {notes.map((note) => (
            <TableRow
              key={note.id}
              className="cursor-pointer"
              onClick={() => onOpen(note)}
            >
              <TableCell className="py-2 font-medium">
                <div className="truncate">{note.title}</div>
                {note.body && (
                  <div className="mt-0.5 truncate text-xs text-muted-foreground">
                    {note.body.replace(/\s+/g, " ").trim()}
                  </div>
                )}
              </TableCell>
              <TableCell className="py-2 text-sm text-muted-foreground">
                {note.team_id
                  ? teamById.get(note.team_id) ?? "team"
                  : t("common.personal")}
              </TableCell>
              <TableCell className="py-2">
                {note.access_path && (
                  <AccessBadge path={note.access_path} size="sm" />
                )}
              </TableCell>
              <TableCell className="py-2 text-right text-sm text-muted-foreground tabular-nums">
                {formatRelative(note.updated_at, t)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function NoteTableSkeleton({ t }: { t: TFn }) {
  return (
    <div className="rounded-lg border bg-card">
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="h-10 w-[40%]">{t("notes.columnTitle")}</TableHead>
            <TableHead className="h-10">{t("notes.columnScope")}</TableHead>
            <TableHead className="h-10">{t("notes.columnAccess")}</TableHead>
            <TableHead className="h-10 text-right">
              {t("notes.columnUpdated")}
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {Array.from({ length: 6 }).map((_, i) => (
            <TableRow key={i} className="hover:bg-transparent">
              <TableCell className="py-3">
                <Skeleton className="h-4 w-1/2" />
              </TableCell>
              <TableCell className="py-3">
                <Skeleton className="h-4 w-24" />
              </TableCell>
              <TableCell className="py-3">
                <Skeleton className="h-5 w-20" />
              </TableCell>
              <TableCell className="py-3 text-right">
                <Skeleton className="ml-auto h-4 w-16" />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function NoteGrid({
  notes,
  onOpen,
  t,
}: {
  notes: Note[];
  onOpen: (n: Note) => void;
  t: TFn;
}) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {notes.map((note) => (
        <Card
          key={note.id}
          size="sm"
          className="cursor-pointer transition-colors hover:border-foreground/20"
          onClick={() => onOpen(note)}
        >
          <CardHeader className="gap-2">
            <div className="flex items-start justify-between gap-2">
              <CardTitle className="line-clamp-2 text-sm leading-snug">
                {note.title}
              </CardTitle>
            </div>
            {note.access_path && (
              <div>
                <AccessBadge path={note.access_path} size="sm" />
              </div>
            )}
          </CardHeader>
          <CardContent className="pt-0">
            <p className="line-clamp-4 whitespace-pre-wrap text-sm text-muted-foreground">
              {note.body || <em>({t("common.personal").toLowerCase()})</em>}
            </p>
            <div className="mt-3 text-xs text-muted-foreground tabular-nums">
              {formatRelative(note.updated_at, t)}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function NoteGridSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {Array.from({ length: 8 }).map((_, i) => (
        <Card key={i} size="sm">
          <CardHeader className="gap-2">
            <Skeleton className="h-5 w-2/3" />
            <Skeleton className="h-4 w-16" />
          </CardHeader>
          <CardContent className="space-y-2">
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-3 w-11/12" />
            <Skeleton className="h-3 w-3/4" />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function scopeHint(scope: NoteScope, t: TFn): string {
  const resource = RESOURCE.name.toLowerCase();
  if (scope === "mine") return t("notes.scopeMine", { resource });
  if (scope === "team") return t("notes.scopeTeam");
  if (scope === "shared") return t("notes.scopeShared");
  return t("notes.scopeOrg");
}

function formatRelative(iso: string, t: TFn): string {
  const then = new Date(iso).getTime();
  const diff = Date.now() - then;
  const mins = Math.round(diff / 60_000);
  if (mins < 1) return t("notes.updatedJust");
  if (mins < 60) return t("notes.updatedMinutes", { count: mins });
  const hours = Math.round(mins / 60);
  if (hours < 24) return t("notes.updatedHours", { count: hours });
  const days = Math.round(hours / 24);
  if (days < 30) return t("notes.updatedDays", { count: days });
  return new Date(iso).toLocaleDateString();
}
