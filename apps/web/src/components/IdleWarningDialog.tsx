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

export function IdleWarningDialog({
  open,
  secondsLeft,
  onStay,
  onSignOutNow,
}: {
  open: boolean;
  secondsLeft: number;
  onStay: () => void;
  onSignOutNow: () => void;
}) {
  const { t } = useT();
  return (
    <Dialog open={open}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("idle.title")}</DialogTitle>
          <DialogDescription>
            {t("idle.body", { seconds: formatCountdown(secondsLeft) })}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={onSignOutNow}>
            {t("idle.signOutNow")}
          </Button>
          <Button onClick={onStay}>{t("idle.stay")}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function formatCountdown(totalSeconds: number): string {
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  if (m > 0) return `${m}m ${s.toString().padStart(2, "0")}s`;
  return `${s}s`;
}
