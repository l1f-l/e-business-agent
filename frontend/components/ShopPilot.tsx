"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2 } from "lucide-react";
import { api, ApiError, searchByImage, type AuthResult } from "@/lib/api";
import { clearSession, getStoredUser, getToken, saveSession } from "@/lib/auth";
import { CartProvider, useCart } from "@/lib/cart";
import { streamChat } from "@/lib/sse";
import type { ImagePayload } from "./Composer";
import type {
  Block,
  Cart,
  ChatMessage,
  CompareBlock,
  ImageFeatures,
  MetaEvent,
  OrderInfo,
  PlanStep,
  Product,
  RefundInfo,
  ReviewSummary,
  SuggestData,
  User,
} from "@/lib/types";
import AppHeader from "./AppHeader";
import CartDrawer from "./CartDrawer";
import ChatStream from "./ChatStream";
import Composer from "./Composer";
import LoginCard from "./LoginCard";
import ProductRail from "./ProductRail";

const uid = () => Math.random().toString(36).slice(2, 10);
const newSession = () =>
  typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `s-${uid()}`;

export default function ShopPilot() {
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    const token = getToken();
    const cached = getStoredUser();
    if (!token || !cached) {
      setChecking(false);
      return;
    }
    api<{ user: User }>("/api/auth/me")
      .then((data) => {
        saveSession(token, data.user);
        setUser(data.user);
      })
      .catch(() => {
        clearSession();
        setUser(null);
      })
      .finally(() => setChecking(false));
  }, []);

  const handleLogin = (result: AuthResult) => {
    saveSession(result.token, result.user);
    setUser(result.user);
  };

  const handleLogout = () => {
    clearSession();
    setUser(null);
  };

  if (checking) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Loader2 size={18} className="animate-spin text-faint" />
      </div>
    );
  }

  if (!user) return <LoginCard onLogin={handleLogin} />;

  return (
    <CartProvider>
      <Workspace user={user} onLogout={handleLogout} />
    </CartProvider>
  );
}

function Workspace({ user, onLogout }: { user: User; onLogout: () => void }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [catalog, setCatalog] = useState<Product[]>([]);
  const [recommended, setRecommended] = useState<Set<string>>(new Set());
  const sessionRef = useRef<string>("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const { apply } = useCart();

  if (!sessionRef.current) sessionRef.current = newSession();

  useEffect(() => {
    api<{ items: Product[] }>("/api/products")
      .then((data) => setCatalog(data.items ?? []))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  const patchMessage = useCallback((id: string, fn: (m: ChatMessage) => ChatMessage) => {
    setMessages((prev) => prev.map((m) => (m.id === id ? fn(m) : m)));
  }, []);

  const appendBlock = useCallback(
    (id: string, block: Block) => patchMessage(id, (m) => ({ ...m, blocks: [...m.blocks, block] })),
    [patchMessage],
  );

  const appendText = useCallback(
    (id: string, text: string) =>
      patchMessage(id, (m) => {
        const blocks = [...m.blocks];
        const last = blocks[blocks.length - 1];
        if (last && last.kind === "text") {
          blocks[blocks.length - 1] = { kind: "text", text: last.text + text };
        } else {
          blocks.push({ kind: "text", text });
        }
        return { ...m, blocks };
      }),
    [patchMessage],
  );

  const updateStep = useCallback(
    (id: string, data: { id: string; status: PlanStep["status"]; detail?: string }) =>
      patchMessage(id, (m) => ({
        ...m,
        blocks: m.blocks.map((b) =>
          b.kind === "plan"
            ? {
                ...b,
                steps: b.steps.map((s) =>
                  s.id === data.id ? { ...s, status: data.status, detail: data.detail ?? s.detail } : s,
                ),
              }
            : b,
        ),
      })),
    [patchMessage],
  );

  const resolveTool = useCallback(
    (id: string, name: string, ok: boolean) =>
      patchMessage(id, (m) => {
        const blocks = [...m.blocks];
        for (let i = blocks.length - 1; i >= 0; i -= 1) {
          const block = blocks[i];
          if (block.kind === "tool" && block.name === name) {
            blocks[i] = { ...block, ok };
            break;
          }
        }
        return { ...m, blocks };
      }),
    [patchMessage],
  );

  const send = useCallback(
    async (raw: string) => {
      const text = raw.trim();
      if (!text || busy) return;

      const assistantId = uid();
      setMessages((prev) => [
        ...prev,
        { id: uid(), role: "user", blocks: [{ kind: "text", text }] },
        { id: assistantId, role: "assistant", blocks: [], streaming: true },
      ]);
      setBusy(true);

      let authFailed = false;

      try {
        await streamChat({ message: text, session_id: sessionRef.current }, (event, data) => {
          switch (event) {
            case "meta": {
              const meta = data as unknown as MetaEvent;
              patchMessage(assistantId, (m) => ({ ...m, intent: meta.intent }));
              break;
            }
            case "plan": {
              const steps = (data.steps as PlanStep[] | undefined) ?? [];
              appendBlock(assistantId, { kind: "plan", steps });
              break;
            }
            case "step": {
              updateStep(assistantId, data as unknown as { id: string; status: PlanStep["status"]; detail?: string });
              break;
            }
            case "products": {
              const items = (data.items as Product[] | undefined) ?? [];
              if (items.length) {
                appendBlock(assistantId, { kind: "products", items });
                setRecommended((prev) => {
                  const next = new Set(prev);
                  items.forEach((p) => next.add(p.id));
                  return next;
                });
              }
              break;
            }
            case "reviews": {
              const summaries = (data.summaries as ReviewSummary[] | undefined) ?? [];
              if (summaries.length) appendBlock(assistantId, { kind: "reviews", summaries });
              break;
            }
            case "compare": {
              appendBlock(assistantId, { kind: "compare", data: data as unknown as CompareBlock });
              break;
            }
            case "tool_call": {
              const name = String(data.name ?? "");
              const args = (data.args as Record<string, unknown> | undefined) ?? {};
              appendBlock(assistantId, { kind: "tool", name, label: labelForTool(name, args), ok: true });
              break;
            }
            case "tool_result": {
              const name = String(data.name ?? "");
              resolveTool(assistantId, name, Boolean(data.ok));
              const order = data.order as OrderInfo | null | undefined;
              if (name === "query_order" && order) {
                appendBlock(assistantId, { kind: "order", data: order });
              }
              break;
            }
            case "cart": {
              apply(data as unknown as Cart);
              break;
            }
            case "refund": {
              appendBlock(assistantId, { kind: "refund", data: data as unknown as RefundInfo });
              break;
            }
            case "suggest": {
              appendBlock(assistantId, { kind: "suggest", data: data as unknown as SuggestData });
              break;
            }
            case "delta": {
              appendText(assistantId, String(data.text ?? ""));
              break;
            }
            case "error": {
              patchMessage(assistantId, (m) => ({ ...m, error: String(data.message ?? "服务暂时不可用") }));
              break;
            }
            case "done": {
              patchMessage(assistantId, (m) => ({ ...m, streaming: false }));
              break;
            }
            default:
              break;
          }
        });
      } catch (err) {
        const message = err instanceof ApiError ? err.message : err instanceof Error ? err.message : "网络异常";
        if (message.includes("登录")) authFailed = true;
        patchMessage(assistantId, (m) => ({ ...m, error: message }));
      } finally {
        setBusy(false);
        patchMessage(assistantId, (m) => ({ ...m, streaming: false }));
      }

      if (authFailed) onLogout();
    },
    [appendBlock, appendText, apply, busy, onLogout, patchMessage, resolveTool, updateStep],
  );

  const sendImage = useCallback(
    async (image: ImagePayload, hint: string) => {
      if (busy) return;
      const userMsgId = uid();
      const assistantId = uid();
      setMessages((prev) => [
        ...prev,
        {
          id: userMsgId,
          role: "user",
          blocks: [
            { kind: "image", dataUrl: image.dataUrl, status: "uploading" },
            ...(hint ? [{ kind: "text" as const, text: hint }] : []),
          ],
        },
        { id: assistantId, role: "assistant", blocks: [], streaming: true },
      ]);
      setBusy(true);

      try {
        const data = await searchByImage({
          image_base64: image.base64,
          mime: image.mime,
          session_id: sessionRef.current,
          hint,
        });

        setMessages((prev) =>
          prev.map((m) =>
            m.id === userMsgId
              ? {
                  ...m,
                  blocks: m.blocks.map((b) =>
                    b.kind === "image" ? { ...b, status: "done" as const } : b,
                  ),
                }
              : m,
          ),
        );

        appendBlock(assistantId, {
          kind: "match",
          features: data.features as ImageFeatures,
          degraded: data.degraded,
        });

        const items = data.products ?? [];
        if (items.length) {
          appendBlock(assistantId, { kind: "products", items });
          setRecommended((prev) => {
            const next = new Set(prev);
            items.forEach((p) => next.add(p.id));
            return next;
          });
        }
        appendText(assistantId, summaryOfImage(data.features, items, data.degraded));
      } catch (err) {
        const message = err instanceof ApiError ? err.message : err instanceof Error ? err.message : "识图失败";
        if (message.includes("登录")) onLogout();
        patchMessage(assistantId, (m) => ({ ...m, error: message }));
        setMessages((prev) =>
          prev.map((m) =>
            m.id === userMsgId
              ? { ...m, blocks: m.blocks.map((b) => (b.kind === "image" ? { ...b, status: "error" as const } : b)) }
              : m,
          ),
        );
      } finally {
        setBusy(false);
        patchMessage(assistantId, (m) => ({ ...m, streaming: false }));
      }
    },
    [appendBlock, appendText, busy, onLogout, patchMessage],
  );

  const reset = () => {
    const old = sessionRef.current;
    sessionRef.current = newSession();
    setMessages([]);
    setRecommended(new Set());
    api(`/api/session/${old}`, { method: "DELETE" }).catch(() => undefined);
  };

  return (
    <div className="flex h-screen overflow-hidden">
      <main className="flex min-w-0 flex-1 flex-col">
        <AppHeader
          user={user}
          busy={busy}
          canReset={messages.length > 0}
          onReset={reset}
          onLogout={onLogout}
        />
        <ChatStream
          messages={messages}
          scrollRef={scrollRef}
          onExample={send}
          displayName={user.display_name}
        />
        <Composer onSend={send} onSendImage={sendImage} busy={busy} />
      </main>

      <ProductRail products={catalog} recommended={recommended} />
      <CartDrawer />
    </div>
  );
}

function labelForTool(name: string, args: Record<string, unknown>): string {
  if (name === "query_order") return `query_order("${args.order_id ?? ""}")`;
  if (name === "add_to_cart") return `add_to_cart("${args.product_id ?? ""}" ×${args.quantity ?? 1})`;
  if (name === "request_refund") return `request_refund("${args.order_id ?? ""}")`;
  return `${name}()`;
}

function summaryOfImage(features: ImageFeatures, items: Product[], degraded: boolean): string {
  if (degraded) {
    if (!items.length) return "这张图我没看清，也没搜到匹配的商品。换个角度再拍一张，或者直接说型号？";
    return `图没太看清，我先按「${features.keywords.slice(0, 2).join(" ")}」找了几款，你看看有没有接近的？`;
  }
  if (!items.length) {
    return `图里看起来是${features.summary}，不过商城里暂时没有同款。要不要我按相近品类帮你找找？`;
  }
  const top = items[0];
  return `图里看起来是${features.summary}，找到 ${items.length} 款相近的，最接近的是 ${top.name}（¥${top.price}）。想先看口碑，还是直接加购？`;
}
