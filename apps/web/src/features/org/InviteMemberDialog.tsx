import { useState } from "react";
import { ApiError } from "@asunset/web-sdk";
import { toast } from "sonner";
import { UserPlus } from "lucide-react";

import { type Role } from "@/api";
import { useInviteMember } from "@/lib/platformHooks";
import { useT } from "@/lib/useT";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import { TempPasswordCallout } from "./TempPasswordCallout";

export function InviteMemberDialog() {
  const { t } = useT();

  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("member");
  // Temp-password mode swaps the form for a one-time copy callout.
  // Cleared when the user dismisses (or the dialog closes), so the
  // password is never stashed in component state across opens.
  const [tempPasswordView, setTempPasswordView] = useState<{
    email: string;
    password: string;
  } | null>(null);

  const reset = () => {
    setEmail("");
    setRole("member");
    setTempPasswordView(null);
  };

  const inviteM = useInviteMember({
    onSuccess: (result) => {
      const recipient = result.member.user.email;

      if (result.delivery === "temporary_password" && result.temporary_password) {
        // Don't auto-close — admin needs to read the password. Toast
        // only as a hint that the dialog has switched modes.
        toast.success(
          t("invite.successTempPassword", { email: recipient }),
        );
        setTempPasswordView({
          email: recipient,
          password: result.temporary_password,
        });
        return;
      }

      const key =
        result.delivery === "magic_link"
          ? "invite.successMagicLink"
          : "invite.successNoMail";
      toast.success(t(key, { email: recipient }));
      reset();
      setOpen(false);
    },
    onError: (e) => {
      // Branch on the structured code, never the message text — the
      // backend emits {code: "already_a_member"} for both invite-409s.
      if (e instanceof ApiError && e.code === "already_a_member") {
        toast.error(t("invite.alreadyMember", { email: email.trim() }));
      } else {
        toast.error(e.message);
      }
    },
  });

  const canSubmit =
    email.trim().length >= 3 && email.trim().includes("@") && !inviteM.isPending;

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) reset();
      }}
    >
      <DialogTrigger asChild>
        <Button size="sm" variant="default">
          <UserPlus className="size-4" />
          {t("invite.button")}
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t("invite.title")}</DialogTitle>
          {!tempPasswordView && (
            <DialogDescription>{t("invite.description")}</DialogDescription>
          )}
        </DialogHeader>
        {tempPasswordView ? (
          <TempPasswordCallout
            email={tempPasswordView.email}
            password={tempPasswordView.password}
            onDismiss={() => {
              reset();
              setOpen(false);
            }}
          />
        ) : (
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              if (canSubmit) inviteM.mutate({ email: email.trim(), role });
            }}
          >
            <div className="space-y-1.5">
              <Label htmlFor="invite-email">{t("invite.emailLabel")}</Label>
              <Input
                id="invite-email"
                type="email"
                autoComplete="off"
                required
                placeholder={t("invite.emailPlaceholder")}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoFocus
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="invite-role">{t("invite.roleLabel")}</Label>
              <Select value={role} onValueChange={(v) => setRole(v as Role)}>
                <SelectTrigger id="invite-role">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="member">{t("common.member")}</SelectItem>
                  <SelectItem value="admin">{t("common.admin")}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <DialogFooter>
              <DialogClose asChild>
                <Button type="button" variant="outline" disabled={inviteM.isPending}>
                  {t("common.cancel")}
                </Button>
              </DialogClose>
              <Button type="submit" disabled={!canSubmit}>
                {inviteM.isPending
                  ? t("invite.submitting")
                  : t("invite.submit")}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
