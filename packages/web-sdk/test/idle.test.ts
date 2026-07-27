import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";

import { useIdleLogout } from "../src/idle";

// Fake timers fake Date.now too (vitest default), which the hook's
// activity clock depends on.
beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

const MIN = 60_000;

describe("useIdleLogout", () => {
  it("fires onLogout after the idle threshold", () => {
    const onLogout = vi.fn();
    renderHook(() =>
      useIdleLogout({ idleMinutes: 15, warningMinutes: 1, onLogout, enabled: true }),
    );
    act(() => vi.advanceTimersByTime(15 * MIN + 1000));
    expect(onLogout).toHaveBeenCalled();
  });

  it("enters the warning window before logout, with a live countdown", () => {
    const onLogout = vi.fn();
    const { result } = renderHook(() =>
      useIdleLogout({ idleMinutes: 15, warningMinutes: 1, onLogout, enabled: true }),
    );
    act(() => vi.advanceTimersByTime(14 * MIN - 1000));
    expect(result.current.warning).toBe(false);
    act(() => vi.advanceTimersByTime(30_000));
    expect(result.current.warning).toBe(true);
    expect(result.current.secondsLeft).toBeLessThanOrEqual(60);
    expect(onLogout).not.toHaveBeenCalled();
  });

  it("activity resets the clock BEFORE the warning…", () => {
    const onLogout = vi.fn();
    const { result } = renderHook(() =>
      useIdleLogout({ idleMinutes: 15, warningMinutes: 1, onLogout, enabled: true }),
    );
    act(() => vi.advanceTimersByTime(10 * MIN));
    act(() => {
      window.dispatchEvent(new Event("mousemove"));
    });
    act(() => vi.advanceTimersByTime(10 * MIN));
    // 20min elapsed but only 10min since activity — no logout, no warning.
    expect(onLogout).not.toHaveBeenCalled();
    expect(result.current.warning).toBe(false);
  });

  it("…but NOT during the warning (mouse over the dialog must not cancel logout)", () => {
    const onLogout = vi.fn();
    const { result } = renderHook(() =>
      useIdleLogout({ idleMinutes: 15, warningMinutes: 1, onLogout, enabled: true }),
    );
    act(() => vi.advanceTimersByTime(14 * MIN + 30_000));
    expect(result.current.warning).toBe(true);
    act(() => {
      window.dispatchEvent(new Event("mousemove"));
    });
    act(() => vi.advanceTimersByTime(31_000));
    expect(onLogout).toHaveBeenCalled();
  });

  it("reset() (the Stay-signed-in button) leaves the warning window", () => {
    const onLogout = vi.fn();
    const { result } = renderHook(() =>
      useIdleLogout({ idleMinutes: 15, warningMinutes: 1, onLogout, enabled: true }),
    );
    act(() => vi.advanceTimersByTime(14 * MIN + 30_000));
    expect(result.current.warning).toBe(true);
    act(() => result.current.reset());
    expect(result.current.warning).toBe(false);
    act(() => vi.advanceTimersByTime(2 * MIN));
    expect(onLogout).not.toHaveBeenCalled();
  });

  it("does nothing when disabled", () => {
    const onLogout = vi.fn();
    renderHook(() =>
      useIdleLogout({ idleMinutes: 15, warningMinutes: 1, onLogout, enabled: false }),
    );
    act(() => vi.advanceTimersByTime(60 * MIN));
    expect(onLogout).not.toHaveBeenCalled();
  });
});
