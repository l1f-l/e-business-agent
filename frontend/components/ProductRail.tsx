"use client";

import { useMemo, useState } from "react";
import { Sparkles } from "lucide-react";
import type { Product } from "@/lib/types";
import ProductCard from "./ProductCard";

type Props = {
  products: Product[];
  recommended: Set<string>;
};

export default function ProductRail({ products, recommended }: Props) {
  const [category, setCategory] = useState<string>("全部");

  const categories = useMemo(() => {
    const set = new Set(products.map((p) => p.category));
    return ["全部", ...Array.from(set)];
  }, [products]);

  const visible = useMemo(() => {
    const list = category === "全部" ? products : products.filter((p) => p.category === category);
    return [...list].sort((a, b) => {
      const ra = recommended.has(a.id) ? 1 : 0;
      const rb = recommended.has(b.id) ? 1 : 0;
      return rb - ra;
    });
  }, [products, category, recommended]);

  return (
    <aside className="hidden h-screen w-[372px] shrink-0 flex-col border-l border-line bg-[#FAF8F4] xl:flex">
      <header className="border-b border-line px-5 pb-4 pt-6">
        <div className="flex items-center justify-between">
          <h2 className="text-[13px] font-medium tracking-tight text-ink">商品库</h2>
          <span className="rounded-full bg-white px-2 py-0.5 text-[10.5px] text-muted ring-1 ring-line">
            {products.length} 件
          </span>
        </div>
        <p className="mt-1 flex items-center gap-1 text-[11px] text-faint">
          <Sparkles size={11} className="text-accent" />
          AI 推荐过的商品会自动高亮
        </p>

        <div className="no-scrollbar mt-3 flex gap-1.5 overflow-x-auto">
          {categories.map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => setCategory(c)}
              className={[
                "shrink-0 rounded-full px-2.5 py-1 text-[11px] transition",
                category === c
                  ? "bg-ink text-white"
                  : "bg-white text-muted ring-1 ring-line hover:text-ink",
              ].join(" ")}
            >
              {c}
            </button>
          ))}
        </div>
      </header>

      <div className="thin-scroll flex-1 overflow-y-auto px-5 py-4">
        <div className="grid grid-cols-2 gap-3">
          {visible.map((p) => (
            <ProductCard key={p.id} product={p} variant="rail" recommended={recommended.has(p.id)} />
          ))}
        </div>
        {visible.length === 0 && (
          <p className="py-10 text-center text-[12px] text-faint">这个分类下暂时没有商品</p>
        )}
        <p className="mt-5 border-t border-dashed border-line pt-4 text-[10.5px] leading-relaxed text-faint">
          演示数据：10 件商品 · 6 笔订单（1001–1006）<br />
          检索路径：预算/品类过滤 → bge 向量召回 → DeepSeek 生成推荐理由
        </p>
      </div>
    </aside>
  );
}
