import { Fragment, useMemo, useState } from "react";
import { useFetcher } from "@asunset/web-sdk";
import { useQuery } from "@tanstack/react-query";
import {
  type ColumnDef,
  type SortingState,
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Download,
  ScrollText,
  Search,
} from "lucide-react";

import { api, type AuditEvent, type Role } from "@/api";
import { CopyButton } from "@/components/CopyButton";
import { PageHeader } from "@/components/PageHeader";
import { useT } from "@/lib/useT";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
import { ErrorState } from "@/components/States";

export function AuditPage({ orgRole }: { orgRole: Role }) {
  const { t } = useT();
  const f = useFetcher();

  const [eventType, setEventType] = useState("");
  const [traceId, setTraceId] = useState("");
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");
  const [limit, setLimit] = useState(100);

  const eventsQ = useQuery({
    queryKey: ["audit", { eventType, traceId, since, until, limit }],
    queryFn: () =>
      api.listAuditEvents(f, {
        event_type: eventType || undefined,
        trace_id: traceId || undefined,
        since: since ? new Date(since).toISOString() : undefined,
        until: until ? new Date(until + "T23:59:59").toISOString() : undefined,
        limit,
      }),
  });

  return (
    <div className="page-container">
      <PageHeader
        title={t("audit.title")}
        description={
          orgRole === "admin" ? t("audit.descAdmin") : t("audit.descMember")
        }
        actions={
          eventsQ.data && eventsQ.data.length > 0 ? (
            <Button
              variant="outline"
              size="sm"
              onClick={() => downloadCsv(eventsQ.data!)}
            >
              <Download className="size-4" />
              {t("common.exportCsv")}
            </Button>
          ) : null
        }
      />

      <Card size="sm">
        <CardContent>
          <div className="grid gap-3 md:grid-cols-5">
            <FilterField label={t("audit.filterEvent")} htmlFor="f-event">
              <div className="relative">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  id="f-event"
                  className="pl-8"
                  placeholder="note.created"
                  value={eventType}
                  onChange={(e) => setEventType(e.target.value)}
                />
              </div>
            </FilterField>
            <FilterField label={t("audit.filterTrace")} htmlFor="f-trace">
              <Input
                id="f-trace"
                placeholder="abc123…"
                value={traceId}
                onChange={(e) => setTraceId(e.target.value)}
              />
            </FilterField>
            <FilterField label={t("audit.filterSince")} htmlFor="f-since">
              <Input
                id="f-since"
                type="date"
                value={since}
                onChange={(e) => setSince(e.target.value)}
              />
            </FilterField>
            <FilterField label={t("audit.filterUntil")} htmlFor="f-until">
              <Input
                id="f-until"
                type="date"
                value={until}
                onChange={(e) => setUntil(e.target.value)}
              />
            </FilterField>
            <FilterField label={t("audit.filterLimit")} htmlFor="f-limit">
              <Select
                value={String(limit)}
                onValueChange={(v) => setLimit(Number(v))}
              >
                <SelectTrigger id="f-limit">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {[50, 100, 250, 500].map((n) => (
                    <SelectItem key={n} value={String(n)}>
                      {n}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </FilterField>
          </div>
        </CardContent>
      </Card>

      {eventsQ.isLoading && <AuditSkeleton />}
      {eventsQ.error && (
        <ErrorState error={eventsQ.error} onRetry={() => eventsQ.refetch()} />
      )}

      {eventsQ.data && eventsQ.data.length === 0 && (
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <ScrollText />
            </EmptyMedia>
            <EmptyTitle>{t("audit.emptyTitle")}</EmptyTitle>
            <EmptyDescription>
              {eventType || traceId || since || until
                ? t("audit.emptyFiltered")
                : t("audit.emptyNone")}
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      )}

      {eventsQ.data && eventsQ.data.length > 0 && (
        <AuditTable events={eventsQ.data} />
      )}
    </div>
  );
}

function FilterField({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={htmlFor} className="text-xs font-medium text-muted-foreground">
        {label}
      </Label>
      {children}
    </div>
  );
}

function AuditTable({ events }: { events: AuditEvent[] }) {
  const { t } = useT();
  const [sorting, setSorting] = useState<SortingState>([
    { id: "timestamp", desc: true },
  ]);
  const [expanded, setExpanded] = useState<string | null>(null);

  const columns = useMemo<ColumnDef<AuditEvent>[]>(
    () => [
      {
        id: "expand",
        header: "",
        enableSorting: false,
        size: 32,
        cell: ({ row }) => (
          <ChevronDown
            className={`size-4 text-muted-foreground transition-transform ${
              expanded === row.original.id ? "rotate-0" : "-rotate-90"
            }`}
          />
        ),
      },
      {
        id: "timestamp",
        accessorFn: (e) => new Date(e.timestamp).getTime(),
        header: t("audit.columnTime"),
        cell: ({ row }) => (
          <span className="whitespace-nowrap font-mono text-xs tabular-nums text-muted-foreground">
            {new Date(row.original.timestamp).toLocaleString()}
          </span>
        ),
      },
      {
        id: "event_type",
        accessorKey: "event_type",
        header: t("audit.columnEvent"),
        cell: ({ row }) => (
          <span className="font-mono text-xs">{row.original.event_type}</span>
        ),
      },
      {
        id: "actor",
        accessorFn: (e) => actorLabel(e),
        header: t("audit.columnActor"),
        cell: ({ row }) => (
          <span className="block max-w-[240px] truncate text-sm text-muted-foreground">
            {actorLabel(row.original)}
          </span>
        ),
      },
      {
        id: "success",
        accessorFn: (e) => (e.success ? 1 : 0),
        header: t("audit.columnStatus"),
        size: 80,
        cell: ({ row }) => (
          <Badge
            variant={row.original.success ? "success" : "destructive"}
            size="sm"
          >
            {row.original.success ? t("common.ok") : t("common.fail")}
          </Badge>
        ),
      },
    ],
    [expanded, t],
  );

  const table = useReactTable({
    data: events,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize: 25 } },
  });

  return (
    <div className="space-y-3">
      <div className="rounded-lg border bg-card">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((hg) => (
              <TableRow key={hg.id} className="hover:bg-transparent">
                {hg.headers.map((h) => {
                  const sortable = h.column.getCanSort();
                  const dir = h.column.getIsSorted();
                  return (
                    <TableHead
                      key={h.id}
                      className="h-10"
                      style={{ width: h.getSize() }}
                    >
                      {h.isPlaceholder ? null : sortable ? (
                        <button
                          type="button"
                          className="inline-flex items-center gap-1.5 text-left hover:text-foreground"
                          onClick={h.column.getToggleSortingHandler()}
                        >
                          {flexRender(
                            h.column.columnDef.header,
                            h.getContext(),
                          )}
                          <SortIcon dir={dir} />
                        </button>
                      ) : (
                        flexRender(h.column.columnDef.header, h.getContext())
                      )}
                    </TableHead>
                  );
                })}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows.map((row) => {
              const isOpen = expanded === row.original.id;
              return (
                <Fragment key={row.id}>
                  <TableRow
                    onClick={() =>
                      setExpanded(isOpen ? null : row.original.id)
                    }
                    data-state={isOpen ? "selected" : undefined}
                    className="cursor-pointer"
                  >
                    {row.getVisibleCells().map((cell) => (
                      <TableCell key={cell.id} className="py-2">
                        {flexRender(
                          cell.column.columnDef.cell,
                          cell.getContext(),
                        )}
                      </TableCell>
                    ))}
                  </TableRow>
                  {isOpen && (
                    <TableRow className="bg-muted/30 hover:bg-muted/30">
                      <TableCell colSpan={columns.length} className="p-0">
                        <EventDetail event={row.original} />
                      </TableCell>
                    </TableRow>
                  )}
                </Fragment>
              );
            })}
          </TableBody>
        </Table>
      </div>
      <TablePagination table={table} total={events.length} />
    </div>
  );
}

function SortIcon({ dir }: { dir: false | "asc" | "desc" }) {
  if (dir === "asc") return <ArrowUp className="size-3.5" />;
  if (dir === "desc") return <ArrowDown className="size-3.5" />;
  return <ArrowUpDown className="size-3.5 opacity-40" />;
}

function TablePagination<T>({
  table,
  total,
}: {
  table: ReturnType<typeof useReactTable<T>>;
  total: number;
}) {
  const { t } = useT();
  const pg = table.getState().pagination;
  const start = pg.pageIndex * pg.pageSize + 1;
  const end = Math.min((pg.pageIndex + 1) * pg.pageSize, total);
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 px-1">
      <div className="text-caption tabular-nums">
        {t("audit.showing", { start, end, total })}
      </div>
      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={() => table.previousPage()}
          disabled={!table.getCanPreviousPage()}
        >
          <ChevronLeft className="size-4" />
          {t("common.previous")}
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => table.nextPage()}
          disabled={!table.getCanNextPage()}
        >
          {t("common.next")}
          <ChevronRight className="size-4" />
        </Button>
      </div>
    </div>
  );
}

function AuditSkeleton() {
  const { t } = useT();
  return (
    <div className="rounded-lg border bg-card">
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="h-10 w-8"></TableHead>
            <TableHead className="h-10 w-44">{t("audit.columnTime")}</TableHead>
            <TableHead className="h-10">{t("audit.columnEvent")}</TableHead>
            <TableHead className="h-10">{t("audit.columnActor")}</TableHead>
            <TableHead className="h-10 w-20">
              {t("audit.columnStatus")}
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {Array.from({ length: 8 }).map((_, i) => (
            <TableRow key={i} className="hover:bg-transparent">
              <TableCell className="py-3">
                <Skeleton className="size-4" />
              </TableCell>
              <TableCell className="py-3">
                <Skeleton className="h-4 w-36" />
              </TableCell>
              <TableCell className="py-3">
                <Skeleton className="h-4 w-40" />
              </TableCell>
              <TableCell className="py-3">
                <Skeleton className="h-4 w-48" />
              </TableCell>
              <TableCell className="py-3">
                <Skeleton className="h-5 w-10" />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function EventDetail({ event }: { event: AuditEvent }) {
  const { t } = useT();
  const rows: [string, string, boolean?][] = [
    [t("audit.detailWhen"), new Date(event.timestamp).toISOString(), true],
    [t("common.event"), event.event_type, true],
    [t("audit.detailAction"), event.action, false],
    [t("common.status"), event.success ? t("common.ok") : t("common.fail"), false],
    [t("common.actor"), actorLabel(event), false],
    [t("audit.detailActorEmail"), event.actor_email ?? "—", true],
    [t("audit.detailActorId"), event.actor_id ?? "—", true],
    [t("audit.detailActorPermissions"), actorPermissionsLabel(event), false],
    [t("audit.detailPermissionGate"), event.permission ?? "—", true],
    [t("audit.detailGrantedVia"), event.permission_path ?? "—", false],
    [t("audit.detailResource"), resourceLabel(event), false],
    [t("audit.detailResourceId"), event.resource_id ?? "—", true],
    [t("audit.detailTrace"), event.trace_id ?? "—", true],
    [t("audit.detailSession"), event.session_id ?? "—", true],
    [t("audit.detailSourceIp"), event.source_ip ?? "—", true],
    [t("audit.detailUserAgent"), event.user_agent ?? "—", false],
  ];

  return (
    <div className="space-y-4 p-4">
      <div className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
        {rows.map(([label, value, mono]) => (
          <div key={label} className="space-y-0.5">
            <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
              {label}
            </div>
            <div
              className={
                "flex items-start gap-1.5 text-xs " +
                (mono ? "font-mono break-all" : "break-words")
              }
            >
              <span className="min-w-0 flex-1">{value}</span>
              {mono && value !== "—" && <CopyButton value={value} />}
            </div>
          </div>
        ))}
      </div>
      <div className="space-y-1.5">
        <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
          {t("audit.payload")}
        </div>
        {Object.keys(event.payload).length === 0 ? (
          <div className="text-xs italic text-muted-foreground">—</div>
        ) : (
          <pre className="overflow-x-auto rounded-md border bg-background p-3 font-mono text-xs">
            {JSON.stringify(event.payload, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
}

function actorLabel(e: AuditEvent): string {
  if (e.actor_display_name)
    return `${e.actor_display_name}${
      e.actor_email ? ` · ${e.actor_email}` : ""
    }`;
  return e.actor_email ?? e.actor_id ?? "—";
}

function resourceLabel(e: AuditEvent): string {
  if (e.resource_label) return `${e.resource_type} "${e.resource_label}"`;
  if (e.resource_type) return `${e.resource_type}:${e.resource_id ?? "—"}`;
  return "—";
}

function actorPermissionsLabel(event: AuditEvent): string {
  const parts: string[] = [];
  if (event.actor_org_role) parts.push(`org: ${event.actor_org_role}`);
  if (event.actor_realm_roles.length > 0)
    parts.push(`realm: ${event.actor_realm_roles.join(", ")}`);
  return parts.join(" · ") || "—";
}

function downloadCsv(events: AuditEvent[]): void {
  const cols = [
    "timestamp",
    "event_type",
    "action",
    "success",
    "actor_email",
    "actor_id",
    "resource_type",
    "resource_id",
    "resource_label",
    "permission",
    "permission_path",
    "source_ip",
    "trace_id",
    "session_id",
  ] as const;
  const header = cols.join(",");
  const rows = events.map((e) =>
    cols
      .map((c) => csvCell((e as Record<string, unknown>)[c]))
      .join(","),
  );
  const blob = new Blob([[header, ...rows].join("\n")], {
    type: "text/csv;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `audit-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

function csvCell(v: unknown): string {
  if (v === null || v === undefined) return "";
  const s = String(v).replace(/"/g, '""');
  return /[",\n]/.test(s) ? `"${s}"` : s;
}
