import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, authHeaders, createApiCore, newCorrelationId } from "../src/fetch";

function mockFetch(resp: { status?: number; body?: string; headers?: HeadersInit }) {
  const status = resp.status ?? 200;
  // Fresh Response per call — bodies are single-use streams — and 204
  // is a null-body status that refuses a body argument.
  const spy = vi.fn().mockImplementation(() =>
    Promise.resolve(
      new Response(status === 204 ? null : (resp.body ?? "{}"), {
        status,
        headers: resp.headers,
      }),
    ),
  );
  vi.stubGlobal("fetch", spy);
  return spy;
}

afterEach(() => vi.unstubAllGlobals());

describe("newCorrelationId", () => {
  it("mints 24 hex chars, unique per call", () => {
    const a = newCorrelationId();
    expect(a).toMatch(/^[0-9a-f]{24}$/);
    expect(newCorrelationId()).not.toBe(a);
  });
});

describe("createApiCore.request", () => {
  it("stamps bearer + correlation id and prefixes the base URL", async () => {
    const spy = mockFetch({ body: `{"ok":true}` });
    const core = createApiCore("https://api.example.test");
    await core.request("/platform/me", { method: "GET" }, { accessToken: "tok123" });

    const [url, init] = spy.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://api.example.test/platform/me");
    const headers = new Headers(init.headers);
    expect(headers.get("Authorization")).toBe("Bearer tok123");
    expect(headers.get("X-Correlation-Id")).toMatch(/^[0-9a-f]{24}$/);
  });

  it("omits Authorization without a token (pre-login requests)", async () => {
    const spy = mockFetch({});
    await createApiCore("").request("/healthz", {}, { accessToken: undefined });
    const headers = new Headers((spy.mock.calls[0] as [string, RequestInit])[1].headers);
    expect(headers.has("Authorization")).toBe(false);
  });

  it("sets Content-Type json only when a body is present", async () => {
    const spy = mockFetch({});
    const core = createApiCore("");
    await core.request("/a", { method: "POST", body: `{"x":1}` }, { accessToken: "t" });
    await core.request("/b", { method: "GET" }, { accessToken: "t" });
    const h1 = new Headers((spy.mock.calls[0] as [string, RequestInit])[1].headers);
    const h2 = new Headers((spy.mock.calls[1] as [string, RequestInit])[1].headers);
    expect(h1.get("Content-Type")).toBe("application/json");
    expect(h2.has("Content-Type")).toBe(false);
  });

  it("resolves undefined on 204", async () => {
    mockFetch({ status: 204, body: "" });
    const out = await createApiCore("").request("/del", { method: "DELETE" }, { accessToken: "t" });
    expect(out).toBeUndefined();
  });

  it("throws ApiError carrying the SERVER-echoed correlation id", async () => {
    mockFetch({
      status: 403,
      body: "forbidden by policy",
      headers: { "X-Correlation-Id": "server-echo-id" },
    });
    const err = await createApiCore("")
      .request("/x", {}, { accessToken: "t" })
      .catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(403);
    expect((err as ApiError).message).toBe("forbidden by policy");
    expect((err as ApiError).correlationId).toBe("server-echo-id");
  });
});

describe("createApiCore.requestText", () => {
  it("returns raw text and never stamps Content-Type", async () => {
    const spy = mockFetch({ body: "a,b,c\n1,2,3" });
    const text = await createApiCore("").requestText(
      "/notes/export",
      { method: "GET" },
      { accessToken: "t" },
    );
    expect(text).toBe("a,b,c\n1,2,3");
    const headers = new Headers((spy.mock.calls[0] as [string, RequestInit])[1].headers);
    expect(headers.has("Content-Type")).toBe(false);
  });
});

describe("authHeaders", () => {
  it("produces the seam shape for foreign clients", () => {
    const h = authHeaders({ accessToken: "tok" });
    expect(h["Authorization"]).toBe("Bearer tok");
    expect(h["X-Correlation-Id"]).toMatch(/^[0-9a-f]{24}$/);
    const anon = authHeaders({ accessToken: undefined });
    expect(anon["Authorization"]).toBeUndefined();
  });
});
