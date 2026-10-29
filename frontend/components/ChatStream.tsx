"use client";

import { ArrowRight, Layers, MessageSquareQuote, PackageSearch, ShoppingCart, Sparkles, Tags } from "lucide-react";
import type { ChatMessage } from "@/lib/types";
import MessageBlocks from "./blocks/MessageBlocks";

type Props = {
  messages: ChatMessage[];
  scrollRef: React.RefObject<HTMLDivElement | null>;
  onExample: (text: string) => void;
  displayName: string;
};

const EXAMPLES = [
  { icon: Tags, label: "预算选购", query: "500元以内降噪耳机" },
  { icon: MessageSquareQuote, label: "口碑评价", query: "这耳机有什么优缺点" },
  { icon: Layers, label: "商品对比", query: "对比一下 p03 和 p04" },
  { icon: ShoppingCart, label: "检索并加购", query: "帮我买一个500元以内的降噪耳机并加购物车" },
  { icon: PackageSearch, label: "订单物流", query: "查一下订单1001的物流" },
  { icon: ArrowRight, label: "申请退款", query: "帮我退掉订单1005" },
];

function UserBubble({ message }: { message: ChatMessage }) {
  const text = message.blocks
    .filter((b): b is Extract<ChatMessage["blocks"][number], { kind: "text" }> => b.kind === "text")
    .map((b) => b.text)
    .join("");
  const image = message.blocks.find((b) => b.kind === "image");

  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] overflow-hidden rounded-2xl rounded-br-md bg-ink text-[14px] leading-relaxed text-white">
        {image && image.kind === "image" && (
          <div className="relative">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={image.dataUrl} alt="上传的商品图" className="max-h-[220px] w-full object-cover" />
            {image.status === "uploading" && (
              <span className="absolute bottom-2 left-2 rounded-full bg-black/55 px-2 py-[3px] text-[10px] text-white backdrop-blur">
                正在识别…
              </span>
            )}
          </div>
        )}
        {text && <div className={image ? "px-4 py-2.5" : "px-4 py-2.5"}>{text}</div>}
      </div>
    </div>
  );
}

export default function ChatStream({ messages, scrollRef, onExample, displayName }: Props) {
  return (
    <div ref={scrollRef} className="thin-scroll flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-3xl px-4 py-6 sm:px-6">
        {messages.length === 0 ? (
          <section className="pt-4">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-white px-2.5 py-1 text-[10.5px] text-muted">
              <Sparkles size={11} className="text-accent" />
              双路 RAG · Function Calling · 多轮记忆
            </span>
            <h2 className="mt-4 text-[26px] font-medium leading-[1.25] tracking-tight text-ink">
              你好，{displayName}
            </h2>
            <p className="mt-2 max-w-[460px] text-[13.5px] leading-relaxed text-muted">
              说预算和用途，我会同时检索商品参数与真实评论；也可以上传图片搜同款、让我查订单、加购或退款。
            </p>

            <div className="mt-6 grid gap-2 sm:grid-cols-2">
              {EXAMPLES.map(({ icon: Icon, label, query }) => (
                <button
                  key={query}
                  type="button"
                  onClick={() => onExample(query)}
                  className="group flex items-center gap-3 rounded-xl border border-line bg-white/80 px-4 py-3 text-left transition hover:border-accent/40 hover:bg-white"
                >
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[#F4F1EA] text-muted transition group-hover:bg-accent-soft group-hover:text-accent">
                    <Icon size={14} />
                  </span>
                  <span className="min-w-0">
                    <span className="block text-[10px] uppercase tracking-[0.08em] text-faint">{label}</span>
                    <span className="block truncate text-[13px] text-ink">{query}</span>
                  </span>
                </button>
              ))}
            </div>

            <p className="mt-4 text-[10.5px] leading-relaxed text-faint">
              退款示例使用「苏晴 u1003」账号；其他账号会看到越权拦截，这是有意设计的权限校验。
            </p>
          </section>
        ) : (
          <div className="space-y-6">
            {messages.map((message) =>
              message.role === "user" ? (
                <UserBubble key={message.id} message={message} />
              ) : (
                <div key={message.id} className="flex gap-3">
                  <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-[10px] font-medium text-accent">
                    SP
                  </div>
                  <div className="min-w-0 flex-1">
                    <MessageBlocks message={message} onAsk={onExample} />
                  </div>
                </div>
              ),
            )}
          </div>
        )}
      </div>
    </div>
  );
}
