"use client";

import { ImageIcon, ScanSearch } from "lucide-react";
import type { ImageFeatures } from "@/lib/types";

type Props = {
  features: ImageFeatures;
  degraded: boolean;
  reason?: string;
};

const REASON: Record<string, string> = {
  no_api_key: "没配置视觉模型，先按你输入的文字找了",
  vision_failed: "识图服务没响应，先按你输入的文字找了",
  vision_disabled: "识图功能已关闭，先按文字找了",
  empty_response: "没看清图片内容，先按文字找了",
  no_keywords: "没提取到有效特征，先按文字找了",
};

export default function ImageMatchCard({ features, degraded, reason }: Props) {
  const chips = [features.category, ...features.colors, features.form, ...features.features].filter(
    Boolean,
  ) as string[];

  return (
    <div className="mb-3 rounded-2xl border border-line bg-[#FBFAF7] px-3.5 py-3">
      <div className="flex items-start gap-2.5">
        <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent">
          {degraded ? <ImageIcon size={13} /> : <ScanSearch size={13} />}
        </span>

        <div className="min-w-0">
          <p className="text-[11px] uppercase tracking-[0.06em] text-faint">
            {degraded ? "文字兜底检索" : `识别为 · 置信度 ${Math.round(features.confidence * 100)}%`}
          </p>
          <p className="mt-0.5 text-[13.5px] font-medium text-ink">{features.summary}</p>

          {chips.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {chips.slice(0, 6).map((chip) => (
                <span
                  key={chip}
                  className="rounded-full border border-line bg-white px-2 py-[2px] text-[10.5px] text-muted"
                >
                  {chip}
                </span>
              ))}
            </div>
          )}

          {degraded && (
            <p className="mt-1.5 text-[10.5px] leading-relaxed text-faint">
              {REASON[reason ?? ""] ?? "识图没成功，已按文字关键词检索"}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
