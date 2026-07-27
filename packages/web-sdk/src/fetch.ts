/**
 * The asunset fetch core: every request to an asunset-backed API carries
 * a Bearer token and a freshly-minted X-Correlation-Id, so the FastAPI
 * correlation middleware (and every downstream log line, audit row, and
 * SIEM event) can tie the browser action to one trace.
 */

export function newCorrelationId(): string {
  return Array.from(crypto.getRandomValues(new Uint8Array(12)))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly correlationId: string,
    /**
     * Stable machine-readable error code when the API provides one
     * (`{"detail": {"code": "...", "message": "..."}}`). Branch UI on
     * THIS, never by matching message strings — messages are copy,
     * codes are contract.
     */
    public readonly code?: string,
  ) {
    super(message);
  }
}

/** Extract {message, code} from an error body (FastAPI detail shapes). */
export function parseErrorBody(text: string, fallback: string): {
  message: string;
  code?: string;
} {
  let message = text || fallback;
  let code: string | undefined;
  try {
    const detail: unknown = (JSON.parse(text) as { detail?: unknown }).detail;
    if (typeof detail === "string") {
      message = detail;
    } else if (detail && typeof detail === "object") {
      const d = detail as { message?: unknown; code?: unknown };
      if (typeof d.message === "string") message = d.message;
      if (typeof d.code === "string") code = d.code;
    }
  } catch {
    // non-JSON body — keep the raw text
  }
  return { message, code };
}

export type Fetcher = {
  accessToken: string | undefined;
};

/**
 * The auth headers alone — for wiring foreign fetch seams that manage
 * their own requests (e.g. a client exposing a `headers?: () => Record`
 * option). Mints a new correlation id per call.
 */
export function authHeaders(f: Fetcher): Record<string, string> {
  const headers: Record<string, string> = {
    "X-Correlation-Id": newCorrelationId(),
  };
  if (f.accessToken) {
    headers["Authorization"] = `Bearer ${f.accessToken}`;
  }
  return headers;
}

export type ApiCore = {
  /** JSON in/out. 204 resolves to `undefined`. Non-2xx throws ApiError. */
  request<T>(path: string, init: RequestInit, f: Fetcher): Promise<T>;
  /** Text response (CSV exports etc.). Non-2xx throws ApiError. */
  requestText(path: string, init: RequestInit, f: Fetcher): Promise<string>;
};

/**
 * Build the request functions bound to an API base URL. `baseUrl` is
 * explicit (no env reads in the SDK); pass "" for same-origin paths.
 */
export function createApiCore(baseUrl: string): ApiCore {
  async function send(
    path: string,
    init: RequestInit,
    { accessToken }: Fetcher,
    json: boolean,
  ): Promise<Response> {
    const correlationId = newCorrelationId();
    const headers = new Headers(init.headers);
    headers.set("X-Correlation-Id", correlationId);
    if (json && init.body && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    if (accessToken) {
      headers.set("Authorization", `Bearer ${accessToken}`);
    }
    const resp = await fetch(`${baseUrl}${path}`, { ...init, headers });
    if (!resp.ok) {
      const text = await resp.text().catch(() => "");
      const { message, code } = parseErrorBody(text, resp.statusText);
      throw new ApiError(
        resp.status,
        message,
        resp.headers.get("X-Correlation-Id") ?? correlationId,
        code,
      );
    }
    return resp;
  }

  return {
    async request<T>(path: string, init: RequestInit, f: Fetcher): Promise<T> {
      const resp = await send(path, init, f, true);
      if (resp.status === 204) return undefined as T;
      return (await resp.json()) as T;
    },
    async requestText(
      path: string,
      init: RequestInit,
      f: Fetcher,
    ): Promise<string> {
      const resp = await send(path, init, f, false);
      return await resp.text();
    },
  };
}
