"use client";

import { LogOut, RotateCcw, ShoppingBag, UserRound } from "lucide-react";
import { useCart } from "@/lib/cart";
import type { User } from "@/lib/types";

type Props = {
  user: User;
  busy: boolean;
  canReset: boolean;
  onReset: () => void;
  onLogout: () => void;
};

export default function AppHeader({ user, busy, canReset, onReset, onLogout }: Props) {
  const { cart, setOpen } = useCart();

  return (
    <header className="flex items-center justify-between gap-3 border-b border-line bg-canvas/85 px-4 py-3 backdrop-blur sm:px-6">
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-ink text-[11px] font-medium tracking-tight text-white">
          SP
        </div>
        <div>
          <h1 className="text-[14px] font-medium leading-tight tracking-tight text-ink">ShopPilot</h1>
          <p className="flex items-center gap-1.5 text-[10.5px] text-faint">
            <span className="h-1.5 w-1.5 rounded-full bg-pine" />
            AI 导购与客服 · DeepSeek
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <span className="hidden items-center gap-1.5 rounded-full border border-line bg-white px-2.5 py-1 text-[11px] text-muted sm:flex">
          <UserRound size={11} className="text-faint" />
          {user.display_name}
          <span className="font-mono text-[10px] text-faint">{user.user_id}</span>
        </span>

        <button
          type="button"
          onClick={() => setOpen(true)}
          className="relative flex h-8 items-center gap-1.5 rounded-full border border-line bg-white px-3 text-[11.5px] text-muted transition hover:border-accent/40 hover:text-accent"
        >
          <ShoppingBag size={13} />
          购物车
          {cart.count > 0 && (
            <span className="ml-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-accent px-1 font-mono text-[9.5px] text-white">
              {cart.count}
            </span>
          )}
        </button>

        <button
          type="button"
          onClick={onReset}
          disabled={busy || !canReset}
          className="hidden h-8 items-center gap-1.5 rounded-full border border-line bg-white px-3 text-[11.5px] text-muted transition hover:text-ink disabled:opacity-40 sm:flex"
        >
          <RotateCcw size={12} />
          新对话
        </button>

        <button
          type="button"
          onClick={onLogout}
          aria-label="退出登录"
          className="flex h-8 w-8 items-center justify-center rounded-full border border-line bg-white text-muted transition hover:text-ink"
        >
          <LogOut size={13} />
        </button>
      </div>
    </header>
  );
}
