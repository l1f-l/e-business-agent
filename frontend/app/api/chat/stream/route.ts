import { NextRequest } from "next/server";

const BACKEND = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  const body = await req.text();
  const token = req.headers.get("authorization");

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "text/event-stream",
  };
  if (token) headers.Authorization = token;

  let upstream: Response;
  try {
    upstream = await fetch(`${BACKEND}/api/chat/stream`, {
      method: "POST",
      headers,
      body,
      cache: "no-store",
    });
  } catch {
    return new Response(
      `event: error\ndata: ${JSON.stringify({ code: "backend_unreachable", message: "后端未启动" })}\n\n`,
      { status: 200, headers: { "Content-Type": "text/event-stream; charset=utf-8" } },
    );
  }

  if (upstream.status === 401) {
    const detail = await upstream.text();
    return new Response(detail, {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });
  }

  if (!upstream.body) {
    return new Response("event: error\ndata: {}\n\n", {
      status: 502,
      headers: { "Content-Type": "text/event-stream; charset=utf-8" },
    });
  }

  return new Response(upstream.body, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
