import { useAuth } from "@asunset/web-sdk";
import { LogOut, ShieldCheck, ShieldOff } from "lucide-react";

import { useT } from "@/lib/useT";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SettingRow, SettingRowGroup } from "../SettingRow";
import { useSettings } from "../SettingsContext";

export function SecuritySection() {
  const auth = useAuth();
  const { t } = useT();
  const { requestLogout, closeSettings } = useSettings();
  const profile = (auth.user?.profile ?? {}) as Record<string, unknown>;
  const amr = Array.isArray(profile.amr) ? (profile.amr as string[]) : [];
  const hasMfa = amr.some((m) =>
    ["mfa", "otp", "totp", "hwk"].includes(m.toLowerCase()),
  );
  const expiresAt = auth.user?.expires_at
    ? new Date(auth.user.expires_at * 1000)
    : null;

  return (
    <SettingRowGroup>
      <SettingRow
        label={t("settings.security.mfa")}
        helper={t("settings.security.mfaHint")}
      >
        {hasMfa ? (
          <Badge variant="success" size="sm">
            <ShieldCheck className="size-3" />
            {t("settings.security.mfaVerified")}
          </Badge>
        ) : amr.length > 0 ? (
          <Badge variant="soft" size="sm">
            {t("settings.security.mfaSignedInWith", { amr: amr.join(", ") })}
          </Badge>
        ) : (
          <Badge variant="warning" size="sm">
            <ShieldOff className="size-3" />
            {t("settings.security.mfaNotUsed")}
          </Badge>
        )}
      </SettingRow>

      <SettingRow
        label={t("settings.security.sessionExpires")}
        helper={t("settings.security.sessionHint")}
      >
        <span className="text-sm tabular-nums text-muted-foreground">
          {expiresAt ? expiresAt.toLocaleString() : "—"}
        </span>
      </SettingRow>

      <SettingRow
        label={t("settings.security.signOutAll")}
        helper={t("settings.security.signOutAllHint")}
      >
        <Button
          variant="outline"
          onClick={() => {
            closeSettings();
            requestLogout();
          }}
        >
          <LogOut className="size-4" />
          {t("common.signOut")}
        </Button>
      </SettingRow>
    </SettingRowGroup>
  );
}
