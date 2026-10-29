import { createParser } from "eventsource-parser";
import { getToken } from "./auth";

export type SSEHandler = (event: string, data: Record<string, unknown>) => void;

/** 用 POST + ReadableStream 读 SSE（EventSource 不支持带 body 和 Authorization 的 POST）。 */
export async function streamChat(
  body: { message: string; session_id: string },
  onEvent: SSEHandler,
  signal?: AbortSignal,
): Promise<void> {
  const token = getToken();
  const res = await fetch("/api/chat/stream", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      // 双头并行：Authorization 常规部署用，X-Auth-Token 给会覆写 Authorization 的网关用
      ...(token ? { Authorization: `Bearer ${token}`, "X-Auth-Token": token } : {}),
    },
    body: JSON.stringify(body),
    signal,
  });

  if (res.status === 401) {
    throw new Error("登录已失效，请重新登录");
  }
  if (!res.ok || !res.body) {
    throw new Error(`服务返回 ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  const parser = createParser({
    onEvent: (msg) => {
      let data: Record<string, unknown> = {};
      try {
        data = JSON.parse(msg.data);
      } catch {
        data = { text: msg.data };
      }
      onEvent(msg.event ?? "message", data);
    },
  });

  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    parser.feed(decoder.decode(value, { stream: true }));
  }
}
