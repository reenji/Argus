export type User = {
  id: string;
  email: string;
  display_name: string;
  gemini_configured: boolean;
};

export type Session = { access_token: string; token_type: string; user: User };
export type Action = { name: string; description: string };

const HTTP_URL = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");
export const WS_URL = HTTP_URL.replace(/^http/, "ws");

export function getToken() {
  return typeof window === "undefined" ? null : window.localStorage.getItem("argus_session");
}

export function setToken(token: string | null) {
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem("argus_session", token);
  else window.localStorage.removeItem("argus_session");
}

/** An HTTP error from the API, with its status and `detail.code`. */
export class ApiError extends Error {
  constructor(message: string, readonly status: number, readonly code: string | null) {
    super(message);
    this.name = "ApiError";
  }
}

function errorMessage(detail: unknown, status: number) {
  if (typeof detail === "string" && detail) return detail;
  if (detail && typeof detail === "object" && "message" in detail) {
    const { message } = detail as { message?: unknown };
    if (typeof message === "string" && message) return message;
  }
  return `Request failed (${status})`;
}

function errorCode(detail: unknown) {
  if (detail && typeof detail === "object" && "code" in detail) {
    const { code } = detail as { code?: unknown };
    if (typeof code === "string") return code;
  }
  return null;
}

type Listener = () => void;
const unauthorizedListeners = new Set<Listener>();

/** Run handler whenever the server rejects the stored session; returns an unsubscribe. */
export function onUnauthorized(handler: Listener) {
  unauthorizedListeners.add(handler);
  return () => { unauthorizedListeners.delete(handler); };
}

/** Forget the stored token and tell the app to show the sign-in screen. */
export function sessionExpired() {
  setToken(null);
  unauthorizedListeners.forEach((listener) => listener());
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const response = await fetch(`${HTTP_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init.headers,
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    // A 401 on an authenticated call means the token expired or was revoked.
    if (response.status === 401 && token) sessionExpired();
    throw new ApiError(errorMessage(body.detail, response.status), response.status, errorCode(body.detail));
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
