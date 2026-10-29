"use client";

import { useState } from "react";
import { AlertCircle, Loader2, PackageCheck, RotateCcw, Truck } from "lucide-react";
import { api } from "@/lib/api";
import type { OrderInfo, RefundInfo } from "@/lib/types";

const BADGE: Record<string, string> = {
  signed: "bg-[#EAF3DE] text-[#3B6D11]",
  shipped: "bg-accent-soft text-accent-deep",
  delivering: "bg-accent-soft text-accent-deep",
  paid: "bg-[#FAEEDA] text-[#854F0B]",
  refunding: "bg-[#FAEEDA] text-[#854F0B]",
  refunded: "bg-[#EAF3DE] text-[#3B6D11]",
  cancelled: "bg-[#F1EFE8] text-muted",
};

export default function OrderCard({ order }: { order: OrderInfo }) {
  const [refund, setRefund] = useState<RefundInfo | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!order.ok) {
    const forbidden = order.code === "FORBIDDEN";
    return (
      <div className="mb-3 flex items-start gap-2 rounded-2xl border border-[#F0DCC8] bg-[#FDF6EC] px-4 py-3">
        <AlertCircle size={15} className="mt-0.5 shrink-0 text-[#A9701B]" />
        <div className="text-[12px] leading-relaxed text-[#7A5416]">
          <p className="font-medium">
            {forbidden ? "这笔订单不在当前账号下" : `没有查到订单 ${order.order_id}`}
          </p>
          <p className="mt-0.5 text-[11px] text-[#96703A]">
            {forbidden
              ? "出于账号安全，只能查询和操作自己的订单。"
              : `请核对订单号。当前账号可查：${(order.available_order_ids ?? []).join("、") || "—"}`}
          </p>
        </div>
      </div>
    );
  }

  const events = (order.events ?? []).slice(-3).reverse();
  const statusText = refund?.ok ? refund.status_text ?? "退款处理中" : order.status_text;
  const statusKey = refund?.ok ? "refunding" : order.status ?? "";

  const submitRefund = async () => {
    if (busy || !order.order_id) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api<RefundInfo>(`/api/orders/${order.order_id}/refund`, {
        method: "POST",
        body: JSON.stringify({ reason: "用户在对话中申请" }),
      });
      setRefund(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "退款提交失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mb-3 overflow-hidden rounded-2xl border border-line bg-surface">
      <div className="flex items-center justify-between border-b border-line/80 px-4 py-3">
        <div className="flex items-center gap-2">
          <PackageCheck size={16} className="text-pine" />
          <div>
            <p className="text-[10px] uppercase tracking-wide text-faint">订单</p>
            <p className="font-mono text-[13px] font-medium leading-tight text-ink">{order.order_id}</p>
          </div>
        </div>
        <span className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${BADGE[statusKey] ?? "bg-[#F1EFE8] text-muted"}`}>
          {statusText}
        </span>
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 px-4 py-3 text-[12px]">
        <div>
          <dt className="text-[10px] text-faint">商品</dt>
          <dd className="text-ink">
            {order.product_name} <span className="text-muted">×{order.qty}</span>
          </dd>
        </div>
        <div>
          <dt className="text-[10px] text-faint">实付</dt>
          <dd className="font-medium text-accent">¥{order.amount?.toFixed(2)}</dd>
        </div>
        <div>
          <dt className="text-[10px] text-faint">承运商</dt>
          <dd className="text-ink">
            {order.carrier ?? "—"}
            {order.tracking_no && (
              <span className="ml-1 font-mono text-[10px] text-faint">{order.tracking_no}</span>
            )}
          </dd>
        </div>
        <div>
          <dt className="text-[10px] text-faint">预计送达</dt>
          <dd className="text-ink">{order.eta ?? "—"}</dd>
        </div>
      </dl>

      {events.length > 0 && (
        <div className="border-t border-line/80 bg-[#FBFAF7] px-4 py-3">
          <div className="mb-2 flex items-center gap-1.5 text-[10px] text-faint">
            <Truck size={12} />
            物流轨迹
          </div>
          <ol className="space-y-2">
            {events.map((e, i) => (
              <li key={`${e.time}-${i}`} className="flex gap-2.5">
                <span className="relative mt-1 flex h-2 w-2 shrink-0 items-center justify-center">
                  <span
                    className={`h-2 w-2 rounded-full ${
                      i === 0 ? "bg-accent" : "border border-[#CFCBC2] bg-white"
                    }`}
                  />
                </span>
                <div className="min-w-0">
                  <p className={`text-[11.5px] leading-snug ${i === 0 ? "text-ink" : "text-muted"}`}>
                    {e.description}
                  </p>
                  <p className="text-[10px] text-faint">
                    {e.time} · {e.location}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      )}

      {(order.refundable || refund) && (
        <div className="flex items-center justify-between gap-2 border-t border-line/80 px-4 py-2.5">
          <span className="text-[10.5px] text-faint">
            {refund?.refund_id ? `退款单 ${refund.refund_id}` : "已签收，可申请退款"}
          </span>
          {!refund && (
            <button
              type="button"
              onClick={submitRefund}
              disabled={busy}
              className="inline-flex items-center gap-1 rounded-full border border-line bg-white px-2.5 py-1 text-[10.5px] text-muted transition hover:border-accent/40 hover:text-accent disabled:opacity-50"
            >
              {busy ? <Loader2 size={10} className="animate-spin" /> : <RotateCcw size={10} />}
              申请退款
            </button>
          )}
        </div>
      )}

      {error && <p className="border-t border-line/80 bg-accent-soft px-4 py-2 text-[10.5px] text-accent-deep">{error}</p>}
    </div>
  );
}
