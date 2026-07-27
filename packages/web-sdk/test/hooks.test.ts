import { afterEach, describe, expect, it, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";

import { createPlatformHooks, platformKeys } from "../src/hooks";
import type { PlatformClient } from "../src/platform";

// useFetcher rides useAuth — control the token from here.
const authState: { user: { access_token: string } | null } = {
  user: { access_token: "tok" },
};
vi.mock("react-oidc-context", () => ({
  useAuth: () => authState,
}));

function makeWrapper(qc: QueryClient) {
  return ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: qc }, children);
}

function stubClient(overrides: Partial<Record<keyof PlatformClient, unknown>>) {
  return overrides as unknown as PlatformClient;
}

afterEach(() => {
  authState.user = { access_token: "tok" };
  vi.clearAllMocks();
});

describe("queries", () => {
  it("gate on the token: no fetch while signed out", async () => {
    authState.user = null;
    const me = vi.fn();
    const hooks = createPlatformHooks(stubClient({ me }));
    const qc = new QueryClient();
    const { result } = renderHook(() => hooks.useMe(), {
      wrapper: makeWrapper(qc),
    });
    expect(result.current.fetchStatus).toBe("idle");
    expect(me).not.toHaveBeenCalled();
  });

  it("fetch with the fetcher once a token exists", async () => {
    const me = vi.fn().mockResolvedValue({ user: { id: "u" } });
    const hooks = createPlatformHooks(stubClient({ me }));
    const qc = new QueryClient();
    const { result } = renderHook(() => hooks.useMe(), {
      wrapper: makeWrapper(qc),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(me).toHaveBeenCalledWith({ accessToken: "tok" });
  });
});

describe("mutations", () => {
  it("invite invalidates the org-members key, then the consumer callback runs", async () => {
    const inviteOrgMember = vi
      .fn()
      .mockResolvedValue({ delivery: "magic_link" });
    const hooks = createPlatformHooks(stubClient({ inviteOrgMember }));
    const qc = new QueryClient();
    const invalidate = vi.spyOn(qc, "invalidateQueries");
    const onSuccess = vi.fn();

    const { result } = renderHook(() => hooks.useInviteMember({ onSuccess }), {
      wrapper: makeWrapper(qc),
    });
    result.current.mutate({ email: "a@x", role: "member" });
    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: platformKeys.orgMembers,
    });
    expect(onSuccess.mock.calls[0][0]).toEqual({ delivery: "magic_link" });
  });

  it("add-team-member is the lookup→add composite, invalidating that team only", async () => {
    const lookupUser = vi.fn().mockResolvedValue({ id: "u9" });
    const addTeamMember = vi.fn().mockResolvedValue({ role: "member" });
    const hooks = createPlatformHooks(stubClient({ lookupUser, addTeamMember }));
    const qc = new QueryClient();
    const invalidate = vi.spyOn(qc, "invalidateQueries");

    const { result } = renderHook(() => hooks.useAddTeamMember(), {
      wrapper: makeWrapper(qc),
    });
    result.current.mutate({ teamId: "t1", email: "b@x", role: "member" });
    await waitFor(() => expect(addTeamMember).toHaveBeenCalled());
    expect(lookupUser).toHaveBeenCalledWith({ accessToken: "tok" }, "b@x");
    expect(addTeamMember).toHaveBeenCalledWith({ accessToken: "tok" }, "t1", {
      user_id: "u9",
      role: "member",
    });
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: platformKeys.teamMembers("t1"),
    });
  });

  it("resend carries the recipient email through to onSuccess", async () => {
    const resendOrgInvite = vi
      .fn()
      .mockResolvedValue({ delivery: "temporary_password", temporary_password: "pw" });
    const hooks = createPlatformHooks(stubClient({ resendOrgInvite }));
    const qc = new QueryClient();
    const onSuccess = vi.fn();

    const { result } = renderHook(() => hooks.useResendInvite({ onSuccess }), {
      wrapper: makeWrapper(qc),
    });
    result.current.mutate({ userId: "u1", email: "who@x" });
    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
    expect(onSuccess.mock.calls[0][0]).toEqual({
      result: { delivery: "temporary_password", temporary_password: "pw" },
      email: "who@x",
    });
  });

  it("errors reach the consumer onError, never a toast (there are none here)", async () => {
    const removeOrgMember = vi.fn().mockRejectedValue(new Error("nope"));
    const hooks = createPlatformHooks(stubClient({ removeOrgMember }));
    const qc = new QueryClient();
    const onError = vi.fn();
    const { result } = renderHook(() => hooks.useRemoveOrgMember({ onError }), {
      wrapper: makeWrapper(qc),
    });
    result.current.mutate({ userId: "u1" });
    await waitFor(() => expect(onError).toHaveBeenCalled());
    expect((onError.mock.calls[0][0] as Error).message).toBe("nope");
  });
});

describe("useFeatureSet", () => {
  it("empty while loading; typed has() after", async () => {
    const meFeatures = vi.fn().mockResolvedValue(["audit.view"]);
    const hooks = createPlatformHooks(stubClient({ meFeatures }));
    const qc = new QueryClient();
    const { result } = renderHook(
      () => hooks.useFeatureSet<"audit.view" | "notes.export">(),
      { wrapper: makeWrapper(qc) },
    );
    expect(result.current.has("audit.view")).toBe(false);
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.has("audit.view")).toBe(true);
    expect(result.current.has("notes.export")).toBe(false);
  });
});
