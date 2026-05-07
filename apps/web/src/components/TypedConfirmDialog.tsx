import { useState } from "react";
import type { ReactNode } from "react";
import { Trans } from "react-i18next";

import { useT } from "@/lib/useT";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";

// Require the user to type a specific phrase before they can trigger a
// destructive action. Used on team/org delete — matches the pattern
// GitHub and Linear use to prevent muscle-memory mistakes on irreversible
// operations that compliance reviewers will ask about.
export function TypedConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmPhrase,
  actionLabel,
  onConfirm,
  busy,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: ReactNode;
  confirmPhrase: string;
  actionLabel?: string;
  onConfirm: () => void;
  busy?: boolean;
}) {
  const { t } = useT();
  const [input, setInput] = useState("");
  const match = input.trim() === confirmPhrase.trim();

  // Reset the typed phrase when the dialog closes. Done in the event
  // handler (per React docs: don't use Effects to respond to user events).
  const handleOpenChange = (next: boolean) => {
    if (!next) setInput("");
    onOpenChange(next);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <FieldGroup>
          <Field>
            <FieldLabel htmlFor="typed-confirm">
              <Trans
                i18nKey="confirm.typePrompt"
                values={{ phrase: confirmPhrase }}
                components={{
                  code: (
                    <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs" />
                  ),
                }}
              />
            </FieldLabel>
            <Input
              id="typed-confirm"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              autoComplete="off"
              autoFocus
            />
          </Field>
        </FieldGroup>
        <DialogFooter>
          <Button variant="outline" onClick={() => handleOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button
            variant="destructive"
            disabled={!match || busy}
            onClick={onConfirm}
          >
            {busy && <Spinner className="size-4" />}
            {actionLabel ?? t("common.delete")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
