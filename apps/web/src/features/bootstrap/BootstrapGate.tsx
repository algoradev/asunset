import { useState } from "react";
import { Building2, ChevronRight } from "lucide-react";
import { toast } from "sonner";

import { useBootstrap } from "@/lib/platformHooks";
import { useT } from "@/lib/useT";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";

export function BootstrapGate({ isPlatformAdmin }: { isPlatformAdmin: boolean }) {
  const { t } = useT();
  const [orgName, setOrgName] = useState("");

  const mutation = useBootstrap({
    onSuccess: () => toast.success(t("bootstrap.created")),
    onError: (e) => toast.error(e.message),
  });

  if (!isPlatformAdmin) {
    return (
      <Card>
        <CardHeader>
          <div className="flex size-10 items-center justify-center rounded-md bg-muted">
            <Building2 className="size-5 text-muted-foreground" />
          </div>
          <CardTitle className="text-lg">
            {t("bootstrap.notProvisionedTitle")}
          </CardTitle>
          <CardDescription>{t("bootstrap.notProvisionedDesc")}</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex size-10 items-center justify-center rounded-md bg-muted">
          <Building2 className="size-5 text-muted-foreground" />
        </div>
        <CardTitle className="text-lg">{t("bootstrap.setupTitle")}</CardTitle>
        <CardDescription>{t("bootstrap.setupDesc")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <Field>
          <FieldLabel htmlFor="org-name">{t("bootstrap.orgName")}</FieldLabel>
          <Input
            id="org-name"
            value={orgName}
            onChange={(e) => setOrgName(e.target.value)}
            placeholder={t("bootstrap.orgNamePlaceholder")}
            autoFocus
          />
        </Field>
        <Button
          onClick={() => mutation.mutate({ org_name: orgName.trim() })}
          disabled={orgName.trim().length === 0 || mutation.isPending}
        >
          {mutation.isPending && <Spinner className="size-4" />}
          {mutation.isPending ? t("bootstrap.creating") : t("bootstrap.createOrg")}
          {!mutation.isPending && <ChevronRight className="ml-1 opacity-70" />}
        </Button>
      </CardContent>
    </Card>
  );
}
