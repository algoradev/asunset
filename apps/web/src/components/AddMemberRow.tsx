import { Plus } from "lucide-react";

import type { Role } from "@/api";
import { useT } from "@/lib/useT";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Spinner } from "@/components/ui/spinner";

export function AddMemberRow({
  email,
  onEmailChange,
  role,
  onRoleChange,
  onSubmit,
  busy,
  inputId,
  roleId,
}: {
  email: string;
  onEmailChange: (v: string) => void;
  role: Role;
  onRoleChange: (r: Role) => void;
  onSubmit: () => void;
  busy: boolean;
  inputId: string;
  roleId: string;
}) {
  const { t } = useT();
  const disabled = email.trim().length === 0 || busy;
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (!disabled) onSubmit();
      }}
      className="flex flex-col gap-2 sm:flex-row sm:items-end sm:gap-3"
    >
      <div className="flex-1 space-y-1.5">
        <Label htmlFor={inputId} className="text-xs font-medium text-muted-foreground">
          {t("addMember.email")}
        </Label>
        <Input
          id={inputId}
          type="email"
          placeholder={t("addMember.emailPlaceholder")}
          value={email}
          onChange={(e) => onEmailChange(e.target.value)}
          autoComplete="off"
        />
      </div>
      <div className="space-y-1.5 sm:w-36">
        <Label htmlFor={roleId} className="text-xs font-medium text-muted-foreground">
          {t("common.role")}
        </Label>
        <Select value={role} onValueChange={(v) => onRoleChange(v as Role)}>
          <SelectTrigger id={roleId}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="member">{t("common.member")}</SelectItem>
            <SelectItem value="admin">{t("common.admin")}</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <Button type="submit" disabled={disabled} className="sm:w-24">
        {busy ? <Spinner className="size-4" /> : <Plus className="size-4" />}
        {busy ? t("common.adding") : t("common.add")}
      </Button>
    </form>
  );
}
