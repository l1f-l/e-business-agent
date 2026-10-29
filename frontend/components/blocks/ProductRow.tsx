"use client";

import type { Product } from "@/lib/types";
import ProductCard from "../ProductCard";

export default function ProductRow({ items }: { items: Product[] }) {
  if (!items.length) return null;
  return (
    <div className="mb-3">
      <p className="mb-1.5 text-[10.5px] text-faint">
        {items.length > 1 ? `为你筛出 ${items.length} 款` : "找到这款"}
      </p>
      <div className="no-scrollbar -mx-1 flex gap-2.5 overflow-x-auto px-1 pb-1">
        {items.map((product, index) => (
          <ProductCard key={product.id} product={product} recommended={index === 0 && product.score !== undefined} />
        ))}
      </div>
    </div>
  );
}
