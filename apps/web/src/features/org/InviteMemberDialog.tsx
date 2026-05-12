import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "react-oidc-context";
import { toast } from "sonner";
import { UserPlus } from "lucide-react";

import { api, type InviteResult, type Role } from "@/api";
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

export function InviteMemberDialog() {
  const auth = useAuth();
  const { t } = useT();
  const f = { accessToken: auth.user?.access_token };
  const qc = useQueryClient();

  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("member");

  const inviteM = useMutation<InviteResult, Error, void>({
    mutationFn: () =>
      api.inviteOrgMember(f, { email: email.trim(), role }),
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: ["org-members"] });
      const recipient = result.member.user.email;
      const key =
        result.delivery === "magic_link"
          ? "invite.successMagicLink"
          : result.delivery === "app_email"
            ? "invite.successAppEmail"
            : "invite.successNoMail";
      toast.success(t(key, { email: recipient }));
      setEmail("");
      setRole("member");
      setOpen(false);
    },
    onError: (e) => {
      // Backend returns 409 for "already a member" — surface a friendlier
      // message than the raw status text.
      const msg = e.message || "";
      if (msg.toLowerCase().includes("already a member")) {
        toast.error(t("invite.alreadyMember", { email: email.trim() }));
      } else {
        toast.error(msg);
      }
    },
  });

  const canSubmit =
    email.trim().length >= 3 && email.trim().includes("@") && !inviteM.isPending;

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" variant="default">
          <UserPlus className="size-4" />
          {t("invite.button")}
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t("invite.title")}</DialogTitle>
          <DialogDescription>{t("invite.description")}</DialogDescription>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (canSubmit) inviteM.mutate();
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
      </DialogContent>
    </Dialog>
  );
}
