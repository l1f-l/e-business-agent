"use client";

import { CheckCircle2, RotateCcw, XCircle } from "lucide-react";
import type { RefundInfo } from "@/lib/types";

export default function RefundCard({ data }: { data: RefundInfo }) {
  const ok = data.ok;
  return (
    <div
      className={[
        "mb-3 overflow-hidden rounded-2xl border px-4 py-3",
        ok ? "border-[#CFE3D3] bg-[#F5FAF4]" : "border-[#F0DCC8] bg-[#FDF6EC]",
      ].join(" ")}
    >
      <div className="flex items-start gap-2">
        {ok ? (
          <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-pine" />
        ) : (
          <XCircle size={16} className="mt-0.5 shrink-0 text-[#A9701B]" />
        )}
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <p className={["text-[12.5px] font-medium", ok ? "text-pine" : "text-[#7A5416]"].join(" ")}>
              {ok ? data.status_text ?? "退款处理中" : "退款未提交"}
            </p>
            {data.refund_id && (
              <span className="font-mono text-[10px] text-faint">{data.refund_id}</span>
            )}
          </div>
          <p className="mt-0.5 text-[11.5px] leading-relaxed text-muted">
            {data.message ?? "已收到你的退款申请。"}
          </p>
          <div className="mt-1.5 flex items-center gap-2 text-[10.5px] text-faint">
            <span className="inline-flex items-center gap-1">
              <RotateCcw size={10} />
              订单 {data.order_id}
            </span>
            {typeof data.amount === "number" && <span>¥{data.amount.toFixed(2)}</span>}
            {data.product_name && <span className="truncate">{data.product_name}</span>}
          </div>
        </div>
      </div>
    </div>
  );
}
