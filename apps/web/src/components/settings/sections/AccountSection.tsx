import type { Me } from "@/api";
import { CopyableMono } from "@/components/CopyButton";
import { useT } from "@/lib/useT";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { SettingRow, SettingRowGroup } from "../SettingRow";

export function AccountSection({ me }: { me: Me }) {
  const { t } = useT();
  return (
    <SettingRowGroup>
      <SettingRow label={t("settings.account.name")}>
        <div className="flex items-center gap-2">
          <Avatar className="size-6">
            <AvatarFallback className="text-[10px] font-medium">
              {initials(me.user.display_name, me.user.email)}
            </AvatarFallback>
          </Avatar>
          <span className="text-sm">{me.user.display_name}</span>
        </div>
      </SettingRow>
      <SettingRow
        label={t("settings.account.email")}
        helper={t("settings.account.readOnlyHint")}
      >
        <span className="text-sm text-muted-foreground">{me.user.email}</span>
      </SettingRow>
      {me.org_role && (
        <SettingRow label={t("settings.account.orgRole")}>
          <Badge
            variant={me.org_role === "admin" ? "info" : "soft"}
            size="sm"
          >
            {me.org_role === "admin" ? t("common.admin") : t("common.member")}
          </Badge>
        </SettingRow>
      )}
      <SettingRow
        label={t("settings.account.realmRoles")}
        align="start"
      >
        <div className="flex max-w-[200px] flex-wrap justify-end gap-1">
          {me.realm_roles.length > 0 ? (
            me.realm_roles.map((r) => (
              <Badge key={r} variant="outline" size="sm">
                {r}
              </Badge>
            ))
          ) : (
            <span className="text-xs text-muted-foreground">
              {t("settings.account.noRealmRoles")}
            </span>
          )}
        </div>
      </SettingRow>
      <SettingRow label={t("settings.account.userId")}>
        <CopyableMono
          value={me.user.id}
          className="text-xs text-muted-foreground"
        />
      </SettingRow>
    </SettingRowGroup>
  );
}

function initials(name: string, email: string): string {
  const source = name.trim() || email;
  const parts = source.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }
  return source.slice(0, 2).toUpperCase();
}
