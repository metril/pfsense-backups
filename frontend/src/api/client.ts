// Thin fetch wrapper with CSRF handling and 401→/login redirect.

const BASE = "";   // same-origin; Vite dev-proxies /api to the FastAPI service.

function readCookie(name: string): string | null {
  const m = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
  return m ? decodeURIComponent(m[1]) : null;
}

export class ApiError extends Error {
  constructor(public status: number, public body: unknown, message: string) {
    super(message);
  }
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  init?: RequestInit,
): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");

  if (body !== undefined && !(body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  if (method !== "GET" && method !== "HEAD") {
    const csrf = readCookie("csrftoken");
    if (csrf) headers.set("X-CSRF-Token", csrf);
  }

  const resp = await fetch(`${BASE}${path}`, {
    method,
    credentials: "include",
    headers,
    body:
      body === undefined
        ? undefined
        : body instanceof FormData
          ? body
          : JSON.stringify(body),
  });

  if (resp.status === 401) {
    // Only redirect for API calls — WebSocket upgrade is handled separately.
    window.location.href = "/api/auth/login";
    throw new ApiError(401, null, "not authenticated");
  }

  const ct = resp.headers.get("content-type") ?? "";
  const isJson = ct.includes("application/json");
  const data = isJson ? await resp.json() : await resp.text();

  if (!resp.ok) {
    throw new ApiError(resp.status, data, (data as { detail?: string })?.detail ?? resp.statusText);
  }
  return data as T;
}

export const api = {
  get: <T>(p: string) => request<T>("GET", p),
  post: <T>(p: string, body?: unknown) => request<T>("POST", p, body),
  put: <T>(p: string, body?: unknown) => request<T>("PUT", p, body),
  patch: <T>(p: string, body?: unknown) => request<T>("PATCH", p, body),
  delete: <T = void>(p: string) => request<T>("DELETE", p),

  // Binary download helper (used for "download one file").
  async downloadBlob(path: string): Promise<Blob> {
    const resp = await fetch(`${BASE}${path}`, { credentials: "include" });
    if (resp.status === 401) {
      window.location.href = "/api/auth/login";
      throw new ApiError(401, null, "not authenticated");
    }
    if (!resp.ok) throw new ApiError(resp.status, null, resp.statusText);
    return resp.blob();
  },

  async ensureCsrf(): Promise<void> {
    if (!readCookie("csrftoken")) {
      await request<unknown>("GET", "/api/auth/csrf");
    }
  },
};

export function triggerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
