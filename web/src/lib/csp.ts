// Content-Security-Policy for the web console, built per request with a fresh nonce.
// Scripts run only from this origin or with the nonce Next.js stamps on its own tags;
// the browser may only talk to this origin and the ARGUS API (HTTP and its WebSocket).

export function apiOrigins(apiBaseUrl: string): string[] {
  try {
    const http = new URL(apiBaseUrl);
    const ws = new URL(apiBaseUrl);
    ws.protocol = http.protocol === "https:" ? "wss:" : "ws:";
    return [http.origin, ws.origin];
  } catch {
    return [];
  }
}

export function contentSecurityPolicy(nonce: string, apiBaseUrl: string, isDev: boolean): string {
  const connect = ["'self'", ...apiOrigins(apiBaseUrl)].join(" ");
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${isDev ? " 'unsafe-eval'" : ""}`,
    // React style props become style attributes, which a nonce cannot cover.
    `style-src 'self' ${isDev ? "'unsafe-inline'" : `'nonce-${nonce}'`}`,
    "style-src-attr 'unsafe-inline'",
    "img-src 'self' blob: data:",
    "font-src 'self'",
    `connect-src ${connect}`,
    "media-src 'self' blob:",
    "worker-src 'self' blob:",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    ...(isDev ? [] : ["upgrade-insecure-requests"]),
  ].join("; ");
}
