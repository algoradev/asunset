import { useState } from "react";
import { useAuth } from "react-oidc-context";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function BootstrapGate({ isPlatformAdmin }: { isPlatformAdmin: boolean }) {
  const auth = useAuth();
  const qc = useQueryClient();
  const [orgName, setOrgName] = useState("");

  const mutation = useMutation({
    mutationFn: () =>
      api.bootstrap(
        { accessToken: auth.user?.access_token },
        { org_name: orgName.trim() },
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["me"] }),
  });

  if (!isPlatformAdmin) {
    return (
      <Card className="max-w-xl">
        <CardHeader>
          <CardTitle>Instance not yet provisioned</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          A platform administrator needs to sign in and create the
          organization before you can use this instance.
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="max-w-xl">
      <CardHeader>
        <CardTitle>First-run setup</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">
          Name the organization this instance will serve. You'll be registered
          as its first admin. (Template assumes one org per instance.)
        </p>
        <div className="space-y-2">
          <Label htmlFor="org-name">Organization name</Label>
          <Input
            id="org-name"
            value={orgName}
            onChange={(e) => setOrgName(e.target.value)}
            placeholder="Acme Health"
            autoFocus
          />
        </div>
        {mutation.error && (
          <p className="text-sm text-destructive">
            {(mutation.error as Error).message}
          </p>
        )}
        <Button
          onClick={() => mutation.mutate()}
          disabled={orgName.trim().length === 0 || mutation.isPending}
        >
          {mutation.isPending ? "Creating…" : "Create organization"}
        </Button>
      </CardContent>
    </Card>
  );
}
