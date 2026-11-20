import { NextRequest, NextResponse } from "next/server";
import { contentSecurityPolicy } from "@/lib/csp";

// A fresh nonce per page view; Next.js reads it from the request's CSP header and
// stamps it on its framework scripts, bundles and inline styles.
export function proxy(request: NextRequest) {
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const policy = contentSecurityPolicy(
    nonce,
    process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000",
    process.env.NODE_ENV === "development",
  );

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", policy);

  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", policy);
  return response;
}

export const config = {
  // Pages only: static files and prefetches do not need a nonce.
  matcher: [
    {
      source: "/((?!_next/static|_next/image|favicon.ico).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
