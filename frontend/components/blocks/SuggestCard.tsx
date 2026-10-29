"use client";

import { useState } from "react";
import { Check, Plus, Sparkles, X } from "lucide-react";
import { useCart } from "@/lib/cart";
import type { SuggestData } from "@/lib/types";

type Props = {
  data: SuggestData;
  onAsk?: (text: string) => void;
};

export default function SuggestCard({ data, onAsk }: Props) {
  const { add } = useCart();
  const [state, setState] = useState<"idle" | "busy" | "done">("idle");
  const [hidden, setHidden] = useState(false);

  if (hidden) return null;

  const total = data.items.reduce((sum, item) => sum + item.price, 0);

  const addAll = async () => {
    if (state !== "idle") return;
    setState("busy");
    let ok = false;
    for (const item of data.items) {
      const result = await add(item.id, 1);
      ok = ok || result.ok;
    }
    setState(ok ? "done" : "idle");
  };

  return (
    <div className="relative mb-3 rounded-2xl border border-accent/25 bg-[#FDF7F3] p-3.5">
      <button
        type="button"
        onClick={() => setHidden(true)}
        aria-label="不感兴趣"
        className="absolute right-2.5 top-2.5 flex h-6 w-6 items-center justify-center rounded-full text-faint transition hover:bg-white hover:text-ink"
      >
        <X size={12} />
      </button>

      <div className="flex items-center gap-1.5 text-[10.5px] uppercase tracking-[0.06em] text-accent">
        <Sparkles size={11} />
        搭配建议
      </div>
      <p className="mt-1.5 pr-6 text-[13.5px] leading-relaxed text-ink">{data.text}</p>

      <div className="mt-2.5 grid gap-1.5 sm:grid-cols-2">
        {data.items.map((item) => (
          <div key={item.id} className="flex items-center gap-2 rounded-xl border border-line bg-white p-2">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={item.image} alt={item.name} className="h-10 w-10 shrink-0 rounded-lg object-cover" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-[12px] text-ink">{item.name}</p>
              <p className="text-[11px] text-accent">¥{item.price.toLocaleString("zh-CN")}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-2.5 flex items-center gap-2">
        <button
          type="button"
          onClick={addAll}
          disabled={state !== "idle"}
          className={[
            "inline-flex items-center gap-1 rounded-full px-3 py-1.5 text-[11.5px] transition",
            state === "done"
              ? "bg-[#F2F7F1] text-pine"
              : "bg-accent text-white hover:bg-accent-deep disabled:opacity-60",
          ].join(" ")}
        >
          {state === "done" ? <Check size={11} /> : <Plus size={11} />}
          {state === "done" ? "已加入购物车" : `一起加购 ¥${total}`}
        </button>

        {onAsk && state === "idle" && (
          <button
            type="button"
            onClick={() => onAsk("好的")}
            className="rounded-full border border-line bg-white px-3 py-1.5 text-[11.5px] text-muted transition hover:border-accent/40 hover:text-accent"
          >
            好的，加上
          </button>
        )}
      </div>
    </div>
  );
}
