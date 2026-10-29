"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { api, ApiError } from "./api";
import type { Cart } from "./types";

export const EMPTY_CART: Cart = { items: [], count: 0, total: 0 };

type CartApi = {
  cart: Cart;
  open: boolean;
  busy: boolean;
  setOpen: (open: boolean) => void;
  refresh: () => Promise<void>;
  add: (productId: string, quantity?: number) => Promise<{ ok: boolean; message: string }>;
  setQuantity: (productId: string, quantity: number) => Promise<void>;
  remove: (productId: string) => Promise<void>;
  clear: () => Promise<void>;
  apply: (cart: Cart) => void;
  error: string | null;
};

const CartContext = createContext<CartApi | null>(null);

export function CartProvider({ children }: { children: ReactNode }) {
  const [cart, setCart] = useState<Cart>(EMPTY_CART);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const apply = useCallback((next: Cart) => setCart(next), []);

  const refresh = useCallback(async () => {
    try {
      setCart(await api<Cart>("/api/cart"));
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const guarded = useCallback(
    async <T,>(fn: () => Promise<T>): Promise<T | null> => {
      setBusy(true);
      setError(null);
      try {
        return await fn();
      } catch (err) {
        setError(err instanceof Error ? err.message : "操作失败");
        return null;
      } finally {
        setBusy(false);
      }
    },
    [],
  );

  const add = useCallback(
    async (productId: string, quantity = 1) => {
      const data = await guarded(() =>
        api<{ ok: boolean; message: string; cart: Cart }>("/api/cart/items", {
          method: "POST",
          body: JSON.stringify({ product_id: productId, quantity }),
        }),
      );
      if (data) {
        if (data.cart) setCart(data.cart);
        return { ok: data.ok, message: data.message ?? "" };
      }
      return { ok: false, message: "加购失败，请重试" };
    },
    [guarded],
  );

  const setQuantity = useCallback(
    async (productId: string, quantity: number) => {
      const data = await guarded(() =>
        api<{ cart: Cart }>(`/api/cart/items/${productId}`, {
          method: "PATCH",
          body: JSON.stringify({ quantity }),
        }),
      );
      if (data?.cart) setCart(data.cart);
    },
    [guarded],
  );

  const remove = useCallback(
    async (productId: string) => {
      const data = await guarded(() =>
        api<{ cart: Cart }>(`/api/cart/items/${productId}`, { method: "DELETE" }),
      );
      if (data?.cart) setCart(data.cart);
    },
    [guarded],
  );

  const clear = useCallback(async () => {
    const data = await guarded(() => api<{ cart: Cart }>("/api/cart", { method: "DELETE" }));
    if (data?.cart) setCart(data.cart);
  }, [guarded]);

  const value = useMemo(
    () => ({ cart, open, busy, setOpen, refresh, add, setQuantity, remove, clear, apply, error }),
    [cart, open, busy, refresh, add, setQuantity, remove, clear, apply, error],
  );

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

export function useCart(): CartApi {
  const ctx = useContext(CartContext);
  if (!ctx) throw new Error("useCart 必须在 CartProvider 内使用");
  return ctx;
}
