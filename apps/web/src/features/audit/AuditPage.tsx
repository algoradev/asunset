import { useState } from "react";
import { useAuth } from "react-oidc-context";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight } from "lucide-react";

import { api, type AuditEvent, type Role } from "@/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function AuditPage({ orgRole }: { orgRole: Role }) {
  const auth = useAuth();
  const f = { accessToken: auth.user?.access_token };

  const [eventType, setEventType] = useState("");
  const [traceId, setTraceId] = useState("");
  const [limit, setLimit] = useState(50);

  const eventsQ = useQuery({
    queryKey: ["audit", { eventType, traceId, limit }],
    queryFn: () =>
      api.listAuditEvents(f, {
        event_type: eventType || undefined,
        trace_id: traceId || undefined,
        limit,
      }),
  });

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Audit log</h1>
        <p className="text-sm text-muted-foreground">
          {orgRole === "admin"
            ? "Showing all events for this org."
            : "Showing your own events."}
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Filters</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-3">
          <div className="space-y-2">
            <Label htmlFor="f-event">Event type</Label>
            <Input
              id="f-event"
              placeholder="note.created"
              value={eventType}
              onChange={(e) => setEventType(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="f-trace">Trace ID</Label>
            <Input
              id="f-trace"
              placeholder="abc123…"
              value={traceId}
              onChange={(e) => setTraceId(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="f-limit">Limit</Label>
            <Input
              id="f-limit"
              type="number"
              min={1}
              max={500}
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value) || 50)}
            />
          </div>
        </CardContent>
      </Card>

      {eventsQ.isLoading && (
        <p className="text-muted-foreground text-sm">Loading events…</p>
      )}
      {eventsQ.error && (
        <p className="text-sm text-destructive">
          {(eventsQ.error as Error).message}
        </p>
      )}

      <div className="space-y-2">
        {eventsQ.data?.map((e) => <EventRow key={e.id} event={e} />)}
      </div>
    </div>
  );
}

function EventRow({ event }: { event: AuditEvent }) {
  const [open, setOpen] = useState(false);

  const actorLabel = event.actor_display_name
    ? `${event.actor_display_name}${event.actor_email ? ` · ${event.actor_email}` : ""}`
    : (event.actor_email ?? event.actor_id ?? "—");

  const resourceLabel = event.resource_label
    ? `${event.resource_type} "${event.resource_label}"`
    : event.resource_type
      ? `${event.resource_type}:${event.resource_id ?? "—"}`
      : "—";

  return (
    <Card>
      <button
        className="w-full text-left px-4 py-3 flex items-center gap-3"
        onClick={() => setOpen((v) => !v)}
      >
        {open ? (
          <ChevronDown className="h-4 w-4 text-muted-foreground shrink-0" />
        ) : (
          <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />
        )}
        <span className="text-xs text-muted-foreground tabular-nums w-44 font-mono">
          {new Date(event.timestamp).toLocaleString()}
        </span>
        <span className="text-sm font-medium w-44 truncate">
          {event.event_type}
        </span>
        <span className="text-xs text-muted-foreground truncate flex-1">
          {actorLabel}
        </span>
        <span
          className={
            "ml-auto text-xs shrink-0 " +
            (event.success ? "text-muted-foreground" : "text-destructive")
          }
        >
          {event.success ? "ok" : "fail"}
        </span>
      </button>

      {open && (
        <CardContent className="border-t pt-3 text-xs space-y-3">
          <div className="grid grid-cols-2 gap-x-6 gap-y-3">
            <Field
              label="When"
              value={new Date(event.timestamp).toISOString()}
              mono
            />
            <Field label="Event" value={event.event_type} mono />
            <Field label="Action" value={event.action} />
            <Field label="Status" value={event.success ? "ok" : "fail"} />
            <Field
              label="Actor"
              value={
                event.actor_display_name ||
                event.actor_email ||
                event.actor_id ||
                "—"
              }
            />
            <Field label="Actor email" value={event.actor_email ?? "—"} mono />
            <Field
              label="Actor permissions (at emit)"
              value={actorPermissionsLabel(event)}
            />
            <Field label="Permission gate" value={event.permission ?? "—"} mono />
            <Field label="Granted via" value={event.permission_path ?? "—"} />
            <Field label="Source IP" value={event.source_ip ?? "—"} mono />
            <Field label="Session (sid)" value={event.session_id ?? "—"} mono />
            <Field label="User-Agent" value={event.user_agent ?? "—"} />
            <Field label="Resource" value={resourceLabel} />
            <Field label="Resource ID" value={event.resource_id ?? "—"} mono />
            <Field label="Trace" value={event.trace_id ?? "—"} mono />
            <Field label="Actor ID" value={event.actor_id ?? "—"} mono />
          </div>
          <div>
            <div className="text-muted-foreground mb-1">Payload</div>
            {Object.keys(event.payload).length === 0 ? (
              <div className="text-muted-foreground italic">—</div>
            ) : (
              <pre className="bg-muted rounded p-2 overflow-x-auto font-mono">
                {JSON.stringify(event.payload, null, 2)}
              </pre>
            )}
          </div>
        </CardContent>
      )}
    </Card>
  );
}

function actorPermissionsLabel(event: AuditEvent): string {
  const parts: string[] = [];
  if (event.actor_org_role) parts.push(`org: ${event.actor_org_role}`);
  if (event.actor_realm_roles.length > 0)
    parts.push(`realm: ${event.actor_realm_roles.join(", ")}`);
  return parts.join(" · ") || "—";
}

function Field({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div>
      <div className="text-muted-foreground">{label}</div>
      <div className={mono ? "font-mono break-all" : ""}>{value}</div>
    </div>
  );
}
