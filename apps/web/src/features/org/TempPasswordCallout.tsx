import { useState } from "react";
import { Check, Copy, KeyRound } from "lucide-react";
import { toast } from "sonner";

import { useT } from "@/lib/useT";
import { Button } from "@/components/ui/button";

/**
 * Surfaces a one-time temporary password to the inviting admin.
 *
 * The backend's `temp_password` invite mode returns a password that
 * must be conveyed to the new member out-of-band. This callout is the
 * frontend's only chance to show it — the value is not persisted
 * anywhere recoverable. We use a `<code>` element with monospace +
 * `font-feature-settings` so similar glyphs (0/O, 1/l/I) are visually
 * distinct, and a Copy button so admins don't have to select-and-copy
 * tiny text.
 */
export function TempPasswordCallout({
  email,
  password,
  onDismiss,
}: {
  email: string;
  password: string;
  onDismiss: () => void;
}) {
  const { t } = useT();
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(password);
      setCopied(true);
      toast.success(t("invite.tempPasswordCopied"));
    } catch {
      toast.error(t("common.copyFailed"));
    }
  };

  return (
    <div className="space-y-4">
      <div className="rounded-md border border-warning/40 bg-warning/5 p-4">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 rounded-md bg-warning/10 p-1.5 text-warning">
            <KeyRound className="size-4" />
          </div>
          <div className="space-y-1.5">
            <div className="text-sm font-medium">
              {t("invite.tempPasswordTitle")}
            </div>
            <div className="text-xs text-muted-foreground">
              {t("invite.tempPasswordHint")}
            </div>
          </div>
        </div>
      </div>

      <div className="space-y-1.5">
        <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
          {email}
        </div>
        <div className="flex items-stretch gap-2">
          <code className="flex-1 select-all break-all rounded-md border bg-muted/40 px-3 py-2 font-mono text-sm tabular-nums">
            {password}
          </code>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={copy}
            className="shrink-0"
          >
            {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
            {copied
              ? t("invite.tempPasswordCopied")
              : t("invite.tempPasswordCopy")}
          </Button>
        </div>
      </div>

      <div className="flex justify-end">
        <Button type="button" variant="default" onClick={onDismiss}>
          {t("invite.tempPasswordDone")}
        </Button>
      </div>
    </div>
  );
}
