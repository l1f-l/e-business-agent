"use client";

import { useState } from "react";
import { MessageSquareQuote, ThumbsDown, ThumbsUp } from "lucide-react";
import type { ReviewSummary } from "@/lib/types";

function Stars({ rating }: { rating: number }) {
  return (
    <span className="font-mono text-[10.5px] text-[#C08A2E]">
      {"★".repeat(rating)}
      <span className="text-[#DED8CA]">{"★".repeat(5 - rating)}</span>
    </span>
  );
}

function SummaryCard({ summary }: { summary: ReviewSummary }) {
  const [expanded, setExpanded] = useState(false);
  const quotes = expanded ? summary.items : summary.items.slice(0, 2);

  return (
    <div className="border-b border-line/70 px-3 py-2.5 last:border-b-0">
      <div className="flex items-baseline justify-between gap-2">
        <h4 className="truncate text-[12.5px] font-medium text-ink">{summary.product_name}</h4>
        <span className="shrink-0 text-[10.5px] text-faint">
          {summary.rating_avg ?? "-"} 分 · {summary.count} 条
        </span>
      </div>

      <div className="mt-1.5 space-y-1">
        {summary.pros.length > 0 && (
          <div className="flex items-start gap-1.5">
            <ThumbsUp size={10} className="mt-[3px] shrink-0 text-pine" />
            <div className="flex flex-wrap gap-1">
              {summary.pros.map((item) => (
                <span
                  key={item.label}
                  className="rounded-full bg-[#F2F7F1] px-1.5 py-[1px] text-[10px] text-pine"
                >
                  {item.label} · {item.count}
                </span>
              ))}
            </div>
          </div>
        )}
        {summary.cons.length > 0 && (
          <div className="flex items-start gap-1.5">
            <ThumbsDown size={10} className="mt-[3px] shrink-0 text-accent-deep" />
            <div className="flex flex-wrap gap-1">
              {summary.cons.map((item) => (
                <span
                  key={item.label}
                  className="rounded-full bg-accent-soft px-1.5 py-[1px] text-[10px] text-accent-deep"
                >
                  {item.label} · {item.count}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      <ul className="mt-2 space-y-1.5">
        {quotes.map((item) => (
          <li key={item.id} className="rounded-lg bg-[#FAF8F3] px-2 py-1.5">
            <div className="flex items-center gap-1.5">
              <Stars rating={item.rating} />
              <span className="text-[9.5px] text-faint">{item.author}</span>
            </div>
            <p className="mt-0.5 text-[11px] leading-[1.6] text-ink/80">{item.text}</p>
          </li>
        ))}
      </ul>

      {summary.items.length > 2 && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="mt-1.5 text-[10px] text-faint transition hover:text-accent"
        >
          {expanded ? "收起" : `展开全部 ${summary.items.length} 条`}
        </button>
      )}
    </div>
  );
}

export default function ReviewSummaryBlock({ summaries }: { summaries: ReviewSummary[] }) {
  if (!summaries?.length) return null;
  return (
    <div className="mb-3 overflow-hidden rounded-2xl border border-line bg-white">
      <div className="flex items-center gap-1.5 border-b border-line bg-[#FAF8F3] px-3 py-2">
        <MessageSquareQuote size={12} className="text-accent" />
        <span className="text-[11px] text-muted">真实买家评价</span>
        <span className="ml-auto text-[10px] text-faint">仅归纳评论里出现过的内容</span>
      </div>
      {summaries.map((summary) => (
        <SummaryCard key={summary.product_id} summary={summary} />
      ))}
    </div>
  );
}
