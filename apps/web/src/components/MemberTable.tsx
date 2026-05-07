import type { ReactNode } from "react";

import type { Role, User } from "@/api";
import { useT } from "@/lib/useT";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export type MemberRow = {
  user: User;
  role: Role;
  joined_at: string;
};

export function MemberTable({
  rows,
  actions,
  onRoleChange,
  roleBusy,
  showJoined = true,
}: {
  rows: MemberRow[];
  actions?: (row: MemberRow) => ReactNode;
  // When provided, role column becomes editable. Receives userId + new role.
  onRoleChange?: (userId: string, role: Role) => void;
  // userId currently being mutated (disables its Select).
  roleBusy?: string | null;
  showJoined?: boolean;
}) {
  const editable = !!onRoleChange;
  const { t } = useT();
  return (
    <div className="rounded-lg border bg-card">
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="h-10">{t("common.members")}</TableHead>
            <TableHead className="h-10 w-28">{t("common.role")}</TableHead>
            {showJoined && (
              <TableHead className="h-10 w-32">{t("common.joined")}</TableHead>
            )}
            {actions && <TableHead className="h-10 w-16 text-right"></TableHead>}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((m) => (
            <TableRow key={m.user.id} className="hover:bg-muted/40">
              <TableCell className="py-2">
                <div className="flex items-center gap-3">
                  <Avatar className="size-7">
                    <AvatarFallback className="text-[11px] font-medium">
                      {initials(m.user.display_name)}
                    </AvatarFallback>
                  </Avatar>
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium">
                      {m.user.display_name}
                    </div>
                    <div className="truncate text-xs text-muted-foreground">
                      {m.user.email}
                    </div>
                  </div>
                </div>
              </TableCell>
              <TableCell className="py-2">
                {editable ? (
                  <Select
                    value={m.role}
                    disabled={roleBusy === m.user.id}
                    onValueChange={(v) => onRoleChange!(m.user.id, v as Role)}
                  >
                    <SelectTrigger className="h-8 w-24 text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="member">{t("common.member")}</SelectItem>
                      <SelectItem value="admin">{t("common.admin")}</SelectItem>
                    </SelectContent>
                  </Select>
                ) : (
                  <Badge
                    variant={m.role === "admin" ? "info" : "soft"}
                    size="sm"
                  >
                    {m.role === "admin" ? t("common.admin") : t("common.member")}
                  </Badge>
                )}
              </TableCell>
              {showJoined && (
                <TableCell className="py-2 text-sm text-muted-foreground tabular-nums">
                  {new Date(m.joined_at).toLocaleDateString()}
                </TableCell>
              )}
              {actions && (
                <TableCell className="py-2 text-right">
                  {actions(m)}
                </TableCell>
              )}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function initials(name: string): string {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((s) => s[0]?.toUpperCase() ?? "")
    .join("");
}
