import { AlertCircle, RefreshCw } from "lucide-react";

import { useT } from "@/lib/useT";
import { Button } from "./ui/button";
import { Spinner } from "./ui/spinner";

export function LoadingState({ label }: { label?: string }) {
  const { t } = useT();
  return (
    <div
      className="flex items-center gap-2 text-sm text-muted-foreground"
      role="status"
    >
      <Spinner />
      <span>{label ?? t("common.loading")}</span>
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
}: {
  error: unknown;
  onRetry?: () => void;
}) {
  const { t } = useT();
  const message =
    error instanceof Error ? error.message : t("common.someethingWrong");
  return (
    <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4">
      <div className="flex items-start gap-3">
        <AlertCircle className="mt-0.5 size-4 shrink-0 text-destructive" />
        <div className="flex-1 space-y-2">
          <p className="text-sm text-destructive">{message}</p>
          {onRetry && (
            <Button size="sm" variant="outline" onClick={onRetry}>
              <RefreshCw className="size-3.5" />
              {t("common.retry")}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
