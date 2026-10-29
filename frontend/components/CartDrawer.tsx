"use client";

import { Minus, Plus, ShoppingBag, Trash2, X } from "lucide-react";
import { useCart } from "@/lib/cart";

export default function CartDrawer() {
  const { cart, open, setOpen, busy, setQuantity, remove, clear } = useCart();

  return (
    <>
      <div
        onClick={() => setOpen(false)}
        className={[
          "fixed inset-0 z-30 bg-[#1B1B18]/25 transition-opacity duration-300",
          open ? "opacity-100" : "pointer-events-none opacity-0",
        ].join(" ")}
        aria-hidden
      />

      <aside
        className={[
          "fixed right-0 top-0 z-40 flex h-full w-full max-w-[392px] flex-col border-l border-line bg-[#FBFAF7] transition-transform duration-300 ease-out",
          open ? "translate-x-0" : "translate-x-full",
        ].join(" ")}
        aria-label="购物车"
      >
        <header className="flex items-center justify-between border-b border-line px-5 py-4">
          <div>
            <h2 className="flex items-center gap-1.5 text-[13.5px] font-medium text-ink">
              <ShoppingBag size={14} className="text-accent" />
              购物车
              <span className="rounded-full bg-white px-1.5 py-0.5 text-[10px] text-muted ring-1 ring-line">
                {cart.count}
              </span>
            </h2>
            <p className="mt-0.5 text-[10.5px] text-faint">与对话中的加购实时同步</p>
          </div>
          <button
            type="button"
            onClick={() => setOpen(false)}
            aria-label="关闭"
            className="flex h-8 w-8 items-center justify-center rounded-full border border-line bg-white text-muted transition hover:text-ink"
          >
            <X size={14} />
          </button>
        </header>

        <div className="thin-scroll flex-1 overflow-y-auto px-4 py-3">
          {cart.items.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[#F1EFE8] text-faint">
                <ShoppingBag size={20} />
              </div>
              <p className="text-[12.5px] text-muted">购物车还是空的</p>
              <p className="max-w-[220px] text-[11px] leading-relaxed text-faint">
                试着对 Agent 说「帮我买一个 500 元以内的降噪耳机」，它会检索并自动加购。
              </p>
            </div>
          ) : (
            <ul className="space-y-2">
              {cart.items.map((item) => (
                <li key={item.product_id} className="flex gap-3 rounded-xl border border-line bg-white p-2.5">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={item.image}
                    alt={item.name}
                    className="h-[62px] w-[62px] shrink-0 rounded-lg bg-[#EFEBE4] object-cover"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-start justify-between gap-2">
                      <p className="truncate text-[12.5px] font-medium text-ink">{item.name}</p>
                      <button
                        type="button"
                        onClick={() => remove(item.product_id)}
                        aria-label="移除"
                        className="shrink-0 text-faint transition hover:text-accent"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                    <p className="mt-0.5 text-[10px] text-faint">{item.category}</p>
                    <div className="mt-1.5 flex items-center justify-between">
                      <div className="flex items-center gap-1 rounded-full border border-line bg-[#FBFAF7] px-1 py-[2px]">
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => setQuantity(item.product_id, item.quantity - 1)}
                          className="flex h-4 w-4 items-center justify-center rounded-full text-muted transition hover:bg-white hover:text-ink disabled:opacity-40"
                          aria-label="减少"
                        >
                          <Minus size={9} />
                        </button>
                        <span className="w-5 text-center font-mono text-[11px] text-ink">{item.quantity}</span>
                        <button
                          type="button"
                          disabled={busy || item.quantity >= item.stock}
                          onClick={() => setQuantity(item.product_id, item.quantity + 1)}
                          className="flex h-4 w-4 items-center justify-center rounded-full text-muted transition hover:bg-white hover:text-ink disabled:opacity-40"
                          aria-label="增加"
                        >
                          <Plus size={9} />
                        </button>
                      </div>
                      <span className="text-[12px] font-medium text-accent">¥{item.subtotal.toFixed(2)}</span>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        <footer className="border-t border-line bg-white px-5 py-4">
          <div className="flex items-baseline justify-between">
            <span className="text-[11px] text-faint">
              共 {cart.count} 件
              {cart.items.length > 0 && (
                <button
                  type="button"
                  onClick={clear}
                  className="ml-2 text-[10.5px] text-faint underline decoration-line transition hover:text-accent"
                >
                  清空
                </button>
              )}
            </span>
            <span className="text-[19px] font-medium text-accent">¥{cart.total.toFixed(2)}</span>
          </div>
          <button
            type="button"
            disabled={cart.items.length === 0}
            onClick={() => window.alert("演示环境：结算流程未接入支付，仅演示加购与金额计算。")}
            className="mt-3 w-full rounded-xl bg-ink py-2.5 text-[13px] font-medium text-white transition hover:bg-black disabled:cursor-not-allowed disabled:bg-[#DCD7CE]"
          >
            去结算
          </button>
        </footer>
      </aside>
    </>
  );
}
