import { afterEach, describe, expect, it, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";

import { useSilentBootstrap } from "../src/bootstrap";

// Controllable stand-in for react-oidc-context's useAuth.
const authState: {
  isLoading: boolean;
  isAuthenticated: boolean;
  activeNavigator?: string;
  signinSilent: ReturnType<typeof vi.fn>;
} = {
  isLoading: false,
  isAuthenticated: false,
  activeNavigator: undefined,
  signinSilent: vi.fn(),
};

vi.mock("react-oidc-context", () => ({
  useAuth: () => authState,
}));

afterEach(() => {
  authState.isLoading = false;
  authState.isAuthenticated = false;
  authState.activeNavigator = undefined;
  authState.signinSilent = vi.fn();
  window.history.replaceState({}, "", "/");
});

describe("useSilentBootstrap", () => {
  it("tries exactly one silent signin when unauthenticated, then reports failed", async () => {
    authState.signinSilent = vi.fn().mockResolvedValue(null);
    const { result } = renderHook(() => useSilentBootstrap());
    await waitFor(() => expect(result.current).toBe("failed"));
    expect(authState.signinSilent).toHaveBeenCalledTimes(1);
  });

  it("returns to pending when the silent signin yields a user (SSO cookie alive)", async () => {
    authState.signinSilent = vi.fn().mockResolvedValue({ access_token: "t" });
    const { result } = renderHook(() => useSilentBootstrap());
    await waitFor(() => expect(authState.signinSilent).toHaveBeenCalled());
    await waitFor(() => expect(result.current).toBe("pending"));
  });

  it("never races a redirect callback (?code= in the URL)", () => {
    window.history.replaceState({}, "", "/?code=abc&state=xyz");
    renderHook(() => useSilentBootstrap());
    expect(authState.signinSilent).not.toHaveBeenCalled();
  });

  it("does not attempt while authenticated or loading", () => {
    authState.isAuthenticated = true;
    renderHook(() => useSilentBootstrap());
    expect(authState.signinSilent).not.toHaveBeenCalled();
  });

  it("reports failed when the silent attempt throws", async () => {
    authState.signinSilent = vi.fn().mockRejectedValue(new Error("no session"));
    const { result } = renderHook(() => useSilentBootstrap());
    await waitFor(() => expect(result.current).toBe("failed"));
  });
});
