import { afterEach, describe, expect, it, vi } from "vitest";

import { createApiCore } from "../src/fetch";
import { createPlatformClient } from "../src/platform";

function spyFetch() {
  const spy = vi
    .fn()
    .mockImplementation(() => Promise.resolve(new Response("{}", { status: 200 })));
  vi.stubGlobal("fetch", spy);
  return spy;
}

afterEach(() => vi.unstubAllGlobals());

const f = { accessToken: "tok" };

function call(spy: ReturnType<typeof vi.fn>, n = 0): { url: string; init: RequestInit } {
  const [url, init] = spy.mock.calls[n] as [string, RequestInit];
  return { url, init };
}

describe("createPlatformClient", () => {
  it("hits the platform endpoints with the right method + path", async () => {
    const spy = spyFetch();
    const platform = createPlatformClient(createApiCore("https://api.test"));

    await platform.me(f);
    await platform.meFeatures(f);
    await platform.bootstrap(f, { org_name: "Acme" });
    await platform.updateOrgMemberRole(f, "u1", "admin");
    await platform.renameTeam(f, "t9", { name: "New Name" });
    await platform.removeTeamMember(f, "t1", "u2");

    expect(call(spy, 0).url).toBe("https://api.test/platform/me");
    expect(call(spy, 1).url).toBe("https://api.test/platform/me/features");
    const boot = call(spy, 2);
    expect(boot.url).toBe("https://api.test/platform/bootstrap");
    expect(boot.init.method).toBe("POST");
    expect(boot.init.body).toBe(`{"org_name":"Acme"}`);
    const patch = call(spy, 3);
    expect(patch.url).toBe("https://api.test/orgs/current/members/u1");
    expect(patch.init.method).toBe("PATCH");
    expect(patch.init.body).toBe(`{"role":"admin"}`);
    const ren = call(spy, 4);
    expect(ren.url).toBe("https://api.test/teams/t9");
    expect(ren.init.method).toBe("PATCH");
    expect(ren.init.body).toBe(`{"name":"New Name"}`);
    const del = call(spy, 5);
    expect(del.url).toBe("https://api.test/teams/t1/members/u2");
    expect(del.init.method).toBe("DELETE");
  });

  it("rides the Tier-1 core: bearer + correlation on every platform call", async () => {
    const spy = spyFetch();
    const platform = createPlatformClient(createApiCore(""));
    await platform.listTeams(f);
    const headers = new Headers(call(spy).init.headers);
    expect(headers.get("Authorization")).toBe("Bearer tok");
    expect(headers.get("X-Correlation-Id")).toMatch(/^[0-9a-f]{24}$/);
  });

  it("audit filters serialize sparsely (no empty params)", async () => {
    const spy = spyFetch();
    const platform = createPlatformClient(createApiCore(""));
    await platform.listAuditEvents(f, {
      event_type: "note.created",
      trace_id: "",
      limit: 50,
    });
    expect(call(spy).url).toBe("/audit/events?event_type=note.created&limit=50");
    await platform.listAuditEvents(f);
    expect(call(spy, 1).url).toBe("/audit/events");
  });

  it("invite result type carries the exactly-once temp password contract", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            member: {
              user: { id: "u", email: "e@x", display_name: "E" },
              role: "member",
              joined_at: "now",
              pending: true,
            },
            delivery: "temporary_password",
            was_new_user: true,
            temporary_password: "one-time-pw",
          }),
          { status: 200 },
        ),
      ),
    );
    const platform = createPlatformClient(createApiCore(""));
    const result = await platform.inviteOrgMember(f, {
      email: "e@x",
      role: "member",
    });
    expect(result.delivery).toBe("temporary_password");
    expect(result.temporary_password).toBe("one-time-pw");
  });
});
