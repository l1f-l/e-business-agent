"use client";

import { useEffect, useState } from "react";
import { Check, Plus } from "lucide-react";
import { useCart } from "@/lib/cart";
import type { Product } from "@/lib/types";

type Props = {
  product: Product;
  variant?: "chat" | "rail";
  recommended?: boolean;
  showAdd?: boolean;
};

export default function ProductCard({ product, variant = "chat", recommended = false, showAdd = true }: Props) {
  const isChat = variant === "chat";
  const match = product.score ? Math.round(product.score * 100) : null;
  const { add, busy } = useCart();
  const [added, setAdded] = useState(false);

  useEffect(() => {
    if (!added) return;
    const timer = setTimeout(() => setAdded(false), 1600);
    return () => clearTimeout(timer);
  }, [added]);

  const handleAdd = async (e: React.MouseEvent) => {
    e.stopPropagation();
    const result = await add(product.id, 1);
    if (result.ok) setAdded(true);
  };

  return (
    <article
      className={[
        "group overflow-hidden rounded-2xl border bg-surface transition",
        isChat ? "w-[178px] shrink-0" : "w-full",
        recommended ? "border-accent/45 shadow-[0_0_0_2px_rgba(194,74,43,0.10)]" : "border-line",
        "hover:border-accent/40",
      ].join(" ")}
    >
      <div className="relative overflow-hidden bg-[#EFEBE4]">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={product.image}
          alt={product.name}
          className={[
            "w-full object-cover transition-transform duration-500 group-hover:scale-[1.04]",
            isChat ? "aspect-[4/3]" : "aspect-[5/4]",
          ].join(" ")}
          loading="lazy"
        />
        {match !== null && (
          <span className="absolute left-2 top-2 rounded-full bg-white/85 px-2 py-[3px] text-[10px] font-medium text-muted backdrop-blur">
            匹配 {match}%
          </span>
        )}
        {recommended && (
          <span className="absolute right-2 top-2 rounded-full bg-accent px-2 py-[3px] text-[10px] font-medium text-white">
            AI 推荐
          </span>
        )}
      </div>

      <div className={isChat ? "p-3" : "p-2.5"}>
        <h3 className="truncate text-[13px] font-medium leading-tight text-ink">{product.name}</h3>
        <p className="clamp-2 mt-1 text-[11px] leading-[1.45] text-muted">{product.tagline}</p>
        <div className="mt-2 flex items-end justify-between">
          <span className="text-[15px] font-medium leading-none text-accent">
            ¥{product.price.toLocaleString("zh-CN")}
          </span>
          {showAdd ? (
            <button
              type="button"
              onClick={handleAdd}
              disabled={busy}
              className={[
                "inline-flex items-center gap-0.5 rounded-full border px-2 py-[3px] text-[10.5px] transition",
                added
                  ? "border-pine/30 bg-[#F2F7F1] text-pine"
                  : "border-line bg-white text-muted hover:border-accent/40 hover:text-accent",
              ].join(" ")}
            >
              {added ? <Check size={10} /> : <Plus size={10} />}
              {added ? "已加购" : "加购"}
            </button>
          ) : (
            <span className="text-[10px] text-faint">{product.category}</span>
          )}
        </div>
      </div>
    </article>
  );
}
