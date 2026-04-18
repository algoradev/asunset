import { useAuth } from "react-oidc-context";
import { useMutation } from "@tanstack/react-query";

import { api, type ReconcileReport } from "@/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function AdminPage() {
  const auth = useAuth();
  const f = { accessToken: auth.user?.access_token };

  const reconcileM = useMutation({
    mutationFn: () => api.reconcileFga(f),
  });

  const report: ReconcileReport | undefined = reconcileM.data;

  return (
    <div className="space-y-6 max-w-3xl">
      <h1 className="text-2xl font-semibold">Admin</h1>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">FGA reconciliation</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Walks the DB → OpenFGA ownership / membership tuples and writes any
            missing ones. Audit-logged. Schedule via{" "}
            <code className="text-xs bg-muted px-1 py-0.5 rounded">
              python -m asunset_api.reconcile
            </code>{" "}
            for cron.
          </p>
          <Button
            onClick={() => reconcileM.mutate()}
            disabled={reconcileM.isPending}
          >
            {reconcileM.isPending ? "Running…" : "Run reconcile now"}
          </Button>

          {reconcileM.error && (
            <p className="text-sm text-destructive">
              {(reconcileM.error as Error).message}
            </p>
          )}

          {report && (
            <div className="space-y-2 pt-2 border-t">
              <div className="grid grid-cols-3 gap-4 text-sm">
                <Stat label="Checked" value={report.checked} />
                <Stat label="Missing" value={report.missing_tuples} />
                <Stat label="Added" value={report.added_tuples} />
              </div>
              {Object.keys(report.drift_by_type).length > 0 ? (
                <div>
                  <div className="text-sm font-medium pt-2">Drift by type</div>
                  <ul className="text-sm text-muted-foreground pl-4 list-disc">
                    {Object.entries(report.drift_by_type).map(([k, v]) => (
                      <li key={k}>
                        {k}: {v}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground pt-2">
                  No drift detected.
                </p>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-2xl font-semibold tabular-nums">{value}</div>
    </div>
  );
}
