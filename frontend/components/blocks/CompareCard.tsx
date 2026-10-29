"use client";

import { Check, Plus, TrendingDown } from "lucide-react";
import { useEffect, useState } from "react";
import { useCart } from "@/lib/cart";
import type { CompareBlock } from "@/lib/types";

type Props = {
  data: CompareBlock;
};

function AddButton({ productId }: { productId: string }) {
  const { add, busy } = useCart();
  const [added, setAdded] = useState(false);

  useEffect(() => {
    if (!added) return;
    const timer = setTimeout(() => setAdded(false), 1600);
    return () => clearTimeout(timer);
  }, [added]);

  return (
    <button
      type="button"
      disabled={busy}
      onClick={async () => {
        const result = await add(productId, 1);
        if (result.ok) setAdded(true);
      }}
      className={[
        "mt-2 inline-flex w-full items-center justify-center gap-1 rounded-lg border py-1.5 text-[11px] transition",
        added
          ? "border-pine/30 bg-[#F2F7F1] text-pine"
          : "border-line bg-white text-muted hover:border-accent/40 hover:text-accent",
      ].join(" ")}
    >
      {added ? <Check size={11} /> : <Plus size={11} />}
      {added ? "已加购" : "加入购物车"}
    </button>
  );
}

export default function CompareCard({ data }: Props) {
  if (!data?.ok) return null;

  const columns = [
    { key: "left" as const, product: data.left },
    { key: "right" as const, product: data.right },
  ];

  return (
    <div className="mb-3 overflow-hidden rounded-2xl border border-line bg-white">
      <div className="flex items-center justify-between border-b border-line bg-[#FAF8F3] px-3 py-2">
        <span className="text-[11px] text-muted">商品对比</span>
        <span className="flex items-center gap-1 text-[10.5px] text-accent">
          <TrendingDown size={11} />
          {data.verdict}
        </span>
      </div>

      <div className="grid grid-cols-2 divide-x divide-line">
        {columns.map(({ key, product }) => (
          <div key={key} className="p-3">
            <div className="mb-2 h-[74px] overflow-hidden rounded-lg bg-[#EFEBE4]">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={product.image} alt={product.name} className="h-full w-full object-cover" />
            </div>
            <h4 className="text-[12.5px] font-medium leading-tight text-ink">{product.name}</h4>
            <p className="mt-0.5 text-[15px] font-medium text-accent">
              ¥{product.price.toLocaleString("zh-CN")}
            </p>
            <p className="mt-1 clamp-2 text-[10.5px] leading-[1.5] text-faint">{product.tagline}</p>
            <AddButton productId={product.id} />
          </div>
        ))}
      </div>

      <dl className="border-t border-line">
        {data.rows.map((row) => (
          <div key={row.label} className="grid grid-cols-[64px_1fr_1fr] items-start gap-2 border-b border-line/60 px-3 py-1.5 last:border-b-0">
            <dt className="text-[10.5px] leading-[1.5] text-faint">{row.label}</dt>
            <dd
              className={[
                "rounded px-1 text-[10.5px] leading-[1.5]",
                row.highlight === "left" ? "bg-[#F2F7F1] text-pine" : "text-ink/80",
              ].join(" ")}
            >
              {row.left}
            </dd>
            <dd
              className={[
                "rounded px-1 text-[10.5px] leading-[1.5]",
                row.highlight === "right" ? "bg-[#F2F7F1] text-pine" : "text-ink/80",
              ].join(" ")}
            >
              {row.right}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
