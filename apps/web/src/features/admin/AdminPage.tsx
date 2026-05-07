import { useAuth } from "react-oidc-context";
import { useMutation } from "@tanstack/react-query";
import { Trans } from "react-i18next";
import { ChevronRight, Play, Shield } from "lucide-react";
import { toast } from "sonner";

import { api, type ReconcileReport } from "@/api";
import { PageHeader } from "@/components/PageHeader";
import { useT } from "@/lib/useT";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Spinner } from "@/components/ui/spinner";

export function AdminPage() {
  const auth = useAuth();
  const { t } = useT();
  const f = { accessToken: auth.user?.access_token };

  const reconcileM = useMutation({
    mutationFn: () => api.reconcileFga(f),
    onSuccess: (r) =>
      toast.success(
        r.missing_tuples === 0
          ? t("admin.toastNoDrift")
          : t("admin.toastFixed", {
              added: r.added_tuples,
              missing: r.missing_tuples,
            }),
      ),
    onError: (e) => toast.error((e as Error).message),
  });

  const report: ReconcileReport | undefined = reconcileM.data;

  return (
    <div className="page-container">
      <PageHeader
        title={t("admin.title")}
        description={t("admin.description")}
      />

      <Card>
        <CardContent className="flex flex-col gap-4">
          <div className="flex items-start gap-3">
            <div className="flex size-9 shrink-0 items-center justify-center rounded-md bg-muted">
              <Shield className="size-5 text-muted-foreground" />
            </div>
            <div className="flex flex-col gap-1">
              <div className="text-card-title">{t("admin.fgaTitle")}</div>
              <p className="text-sm text-muted-foreground">
                <Trans
                  i18nKey="admin.fgaDesc"
                  components={{
                    code: (
                      <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs" />
                    ),
                  }}
                />
              </p>
            </div>
          </div>
          <div>
            <Button
              onClick={() => reconcileM.mutate()}
              disabled={reconcileM.isPending}
            >
              {reconcileM.isPending ? (
                <Spinner className="size-4" />
              ) : (
                <Play className="size-4" />
              )}
              {reconcileM.isPending ? t("admin.running") : t("admin.run")}
              {!reconcileM.isPending && (
                <ChevronRight className="ml-1 opacity-70" />
              )}
            </Button>
          </div>

          {report && (
            <>
              <Separator />
              <div className="grid grid-cols-3 gap-4">
                <Stat label={t("admin.checked")} value={report.checked} />
                <Stat label={t("admin.missing")} value={report.missing_tuples} />
                <Stat label={t("admin.added")} value={report.added_tuples} />
              </div>
              {Object.keys(report.drift_by_type).length > 0 ? (
                <div className="space-y-2">
                  <div className="text-section-title">
                    {t("admin.driftByType")}
                  </div>
                  <ul className="space-y-1 text-sm text-muted-foreground">
                    {Object.entries(report.drift_by_type).map(([k, v]) => (
                      <li key={k} className="flex justify-between">
                        <span className="font-mono text-xs">{k}</span>
                        <span className="tabular-nums">{v}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">
                  {t("admin.noDrift")}
                </p>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border bg-card p-3">
      <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div className="text-2xl font-semibold tabular-nums">{value}</div>
    </div>
  );
}
