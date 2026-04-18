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
  return (
    <Dialog open={open}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>You'll be signed out soon</DialogTitle>
          <DialogDescription>
            For security, inactive sessions are signed out automatically.
            You'll be signed out in{" "}
            <span className="font-semibold tabular-nums">
              {formatCountdown(secondsLeft)}
            </span>
            .
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={onSignOutNow}>
            Sign out now
          </Button>
          <Button onClick={onStay}>Stay signed in</Button>
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
