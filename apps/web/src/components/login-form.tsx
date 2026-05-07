import { ChevronRight, KeyRound } from "lucide-react";

import { BRAND } from "@/config/brand";
import { RESOURCE } from "@/config/resource";
import { cn } from "@/lib/utils";
import { useT } from "@/lib/useT";
import { Button } from "@/components/ui/button";

export function LoginForm({
  onSignIn,
  error,
  className,
  ...props
}: {
  onSignIn: () => void;
  error?: string;
} & Omit<React.ComponentPropsWithoutRef<"div">, "onSubmit">) {
  const { t } = useT();
  const Icon = RESOURCE.icon;
  return (
    <div className={cn("flex flex-col gap-6", className)} {...props}>
      <div className="flex flex-col items-center gap-3 text-center">
        <div className="flex aspect-square size-10 items-center justify-center rounded-lg bg-primary text-primary-foreground">
          <Icon className="size-5" />
        </div>
        <h1 className="text-2xl font-bold">{BRAND.name}</h1>
        <p className="text-balance text-sm text-muted-foreground">
          {t("brand.signInPrompt")}
        </p>
      </div>
      <div className="grid gap-4">
        <Button type="button" className="w-full" onClick={onSignIn}>
          <KeyRound />
          {t("brand.signInButton")}
          <ChevronRight className="ml-auto" />
        </Button>
        {error && (
          <p className="text-center text-sm text-destructive" role="alert">
            {error}
          </p>
        )}
      </div>
      <p className="text-center text-xs text-muted-foreground">
        {t("brand.loginFooter")}
      </p>
    </div>
  );
}
