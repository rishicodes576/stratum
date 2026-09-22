import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const BACKEND = process.env.API_BASE_URL || "http://127.0.0.1:8000";
const COOKIE = "stratum_session";
const paths =
  /^(me|services|signals|overview|events|stream|jobs(?:\/[a-f0-9-]+\/retry)?|incidents(?:\/[a-f0-9-]+(?:\/(?:notes|decisions))?)?|auth\/(?:login|logout))$/;

async function handler(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path: segments } = await context.params;
  const path = segments.join("/");
  if (!paths.test(path)) return NextResponse.json({ detail: "Not found" }, { status: 404 });
  if (!["GET", "HEAD"].includes(request.method)) {
    const origin = request.headers.get("origin");
    const expected = process.env.APP_ORIGIN || request.nextUrl.origin;
    if (!origin || origin !== expected)
      return NextResponse.json({ detail: "Origin rejected" }, { status: 403 });
  }
  if (path === "auth/logout") {
    if (request.method !== "POST")
      return NextResponse.json({ detail: "Method not allowed" }, { status: 405 });
    const result = NextResponse.json({ signed_out: true });
    result.cookies.delete(COOKIE);
    return result;
  }
  const token = request.cookies.get(COOKIE)?.value;
  if (!token && path !== "auth/login")
    return NextResponse.json({ detail: "Sign in to continue" }, { status: 401 });
  const headers = new Headers({ "Content-Type": "application/json" });
  if (token) headers.set("Authorization", `Bearer ${token}`);
  for (const key of ["idempotency-key", "last-event-id"]) {
    const value = request.headers.get(key);
    if (value) headers.set(key, value);
  }
  let body: string | undefined;
  if (!["GET", "HEAD"].includes(request.method)) {
    const reader = request.body?.getReader();
    if (reader) {
      const chunks: Uint8Array[] = [];
      let size = 0;
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        size += value.length;
        if (size > 65536) {
          await reader.cancel();
          return NextResponse.json({ detail: "Request too large" }, { status: 413 });
        }
        chunks.push(value);
      }
      body = Buffer.concat(chunks).toString("utf8");
    }
  }
  try {
    const response = await fetch(`${BACKEND}/v1/${path}${request.nextUrl.search}`, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.any([
        request.signal,
        AbortSignal.timeout(path === "stream" ? 65000 : 20000),
      ]),
    });
    if (path === "auth/login" && response.ok) {
      const result = await response.json();
      const outgoing = NextResponse.json({ signed_in: true });
      outgoing.cookies.set(COOKIE, result.access_token, {
        httpOnly: true,
        sameSite: "strict",
        secure: process.env.COOKIE_SECURE === "true",
        path: "/",
        maxAge: result.expires_in,
      });
      outgoing.headers.set("Cache-Control", "no-store");
      return outgoing;
    }
    const outgoing = new NextResponse(response.body, {
      status: response.status,
      headers: {
        "Content-Type": response.headers.get("content-type") || "application/json",
        "Cache-Control": "no-store",
        "X-Accel-Buffering": "no",
      },
    });
    const retryAfter = response.headers.get("retry-after");
    if (retryAfter) outgoing.headers.set("Retry-After", retryAfter);
    if (response.status === 401) outgoing.cookies.delete(COOKIE);
    return outgoing;
  } catch {
    return NextResponse.json(
      { detail: "The API is unavailable. Check the backend and try again." },
      { status: 502 },
    );
  }
}

export { handler as GET, handler as POST, handler as PATCH };
