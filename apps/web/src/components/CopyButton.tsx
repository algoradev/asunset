import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { toast } from "sonner";

import { useT } from "@/lib/useT";
import { cn } from "@/lib/utils";

// Small inline copy affordance. Wrap a monospace ID next to this button
// so users can grab trace IDs / resource IDs / user UUIDs without
// select-all gymnastics — matches the pattern in Tailscale's admin.
export function CopyButton({
  value,
  className,
  ariaLabel,
}: {
  value: string;
  className?: string;
  ariaLabel?: string;
}) {
  const { t } = useT();
  const [copied, setCopied] = useState(false);

  if (!value || value === "—") return null;

  const onClick = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      toast.success(t("common.copied"));
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error(t("common.someethingWrong"));
    }
  };

  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={ariaLabel ?? t("common.copy")}
      className={cn(
        "inline-flex size-5 shrink-0 items-center justify-center rounded text-muted-foreground/60 transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        className,
      )}
    >
      {copied ? (
        <Check className="size-3 text-success" />
      ) : (
        <Copy className="size-3" />
      )}
    </button>
  );
}

// Convenience wrapper: monospace text + trailing copy button.
// Use for anywhere you'd write `<span className="font-mono">{id}</span>`.
export function CopyableMono({
  value,
  className,
}: {
  value: string;
  className?: string;
}) {
  return (
    <span
      className={cn("inline-flex items-center gap-1.5 font-mono", className)}
    >
      <span className="break-all">{value}</span>
      <CopyButton value={value} />
    </span>
  );
}
