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

function errorMessage(detail: unknown, status: number) {
  if (typeof detail === "string" && detail) return detail;
  if (detail && typeof detail === "object" && "message" in detail) {
    const { message } = detail as { message?: unknown };
    if (typeof message === "string" && message) return message;
  }
  return `Request failed (${status})`;
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
    throw new Error(errorMessage(body.detail, response.status));
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
