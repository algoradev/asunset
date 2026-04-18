import { useEffect, useRef, useState } from "react";

/**
 * HIPAA §164.312(a)(2)(iii) "Automatic logoff" — terminates an electronic
 * session after a predetermined time of inactivity. This hook tracks
 * browser interaction (mouse, keyboard, touch, scroll) and triggers a
 * warning countdown → sign-out when the idle threshold is reached.
 *
 * Server-side SSO idle timeout (Keycloak ssoSessionIdleTimeout) is the
 * authoritative cap — this hook is the UX layer that makes the logoff
 * visible to the user before their next request 401s.
 */

const IDLE_EVENTS = [
  "mousemove",
  "mousedown",
  "keydown",
  "touchstart",
  "scroll",
  "wheel",
] as const;

export type IdleLogoutOptions = {
  /** Minutes of inactivity before sign-out is triggered. Default 15. */
  idleMinutes?: number;
  /** Minutes before logout to show a "stay signed in?" warning. Default 1. */
  warningMinutes?: number;
  /** Called when the idle threshold is reached. */
  onLogout: () => void;
  /** Master switch — pass `false` while the user isn't authenticated. */
  enabled: boolean;
};

export type IdleState = {
  /** Are we currently inside the warning window? */
  warning: boolean;
  /** Seconds until forced logout, while in the warning window. */
  secondsLeft: number;
  /** Reset the idle timer — wire to the "Stay signed in" button. */
  reset: () => void;
};

export function useIdleLogout(opts: IdleLogoutOptions): IdleState {
  const { idleMinutes = 15, warningMinutes = 1, onLogout, enabled } = opts;

  const [warning, setWarning] = useState(false);
  const [secondsLeft, setSecondsLeft] = useState(warningMinutes * 60);
  const lastActivityRef = useRef<number>(Date.now());
  const tickRef = useRef<number | null>(null);

  const reset = () => {
    lastActivityRef.current = Date.now();
    setWarning(false);
    setSecondsLeft(warningMinutes * 60);
  };

  useEffect(() => {
    if (!enabled) return;

    const onActivity = () => {
      // Only bump the activity clock when we're NOT in warning state —
      // otherwise the warning dialog itself (mouse movement on it) would
      // silently reset the timer and the dialog would never fire logout.
      if (!warning) {
        lastActivityRef.current = Date.now();
      }
    };

    IDLE_EVENTS.forEach((ev) =>
      window.addEventListener(ev, onActivity, { passive: true }),
    );

    const idleMs = idleMinutes * 60_000;
    const warnMs = warningMinutes * 60_000;

    tickRef.current = window.setInterval(() => {
      const idleFor = Date.now() - lastActivityRef.current;
      if (idleFor >= idleMs) {
        onLogout();
        return;
      }
      if (idleFor >= idleMs - warnMs) {
        setWarning(true);
        setSecondsLeft(Math.max(0, Math.ceil((idleMs - idleFor) / 1000)));
      } else {
        setWarning(false);
      }
    }, 1000);

    return () => {
      IDLE_EVENTS.forEach((ev) =>
        window.removeEventListener(ev, onActivity),
      );
      if (tickRef.current !== null) {
        window.clearInterval(tickRef.current);
        tickRef.current = null;
      }
    };
  }, [enabled, idleMinutes, warningMinutes, onLogout, warning]);

  return { warning, secondsLeft, reset };
}
