"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, Check, ChevronDown, Circle, Loader2, Minus } from "lucide-react";
import type { PlanStep } from "@/lib/types";

type Props = {
  steps: PlanStep[];
};

const FINAL = new Set(["done", "failed", "skipped"]);

function StepIcon({ status }: { status: PlanStep["status"] }) {
  if (status === "running") return <Loader2 size={12} className="animate-spin text-accent" />;
  if (status === "done") return <Check size={12} className="text-pine" />;
  if (status === "failed") return <AlertTriangle size={12} className="text-accent-deep" />;
  if (status === "skipped") return <Minus size={12} className="text-faint" />;
  return <Circle size={9} className="text-[#C9C4B9]" />;
}

export default function PlanProgress({ steps }: Props) {
  const complete = steps.every((s) => FINAL.has(s.status));
  const failed = steps.some((s) => s.status === "failed");
  const [expanded, setExpanded] = useState(true);

  useEffect(() => {
    if (!complete) {
      setExpanded(true);
      return;
    }
    const timer = setTimeout(() => setExpanded(false), 700);
    return () => clearTimeout(timer);
  }, [complete]);

  if (steps.length === 0) return null;

  const doneCount = steps.filter((s) => s.status === "done").length;

  return (
    <div className="mb-3 overflow-hidden rounded-xl border border-line bg-white/75">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center justify-between px-3 py-2 text-left transition hover:bg-[#FAF8F3]"
      >
        <span className="flex items-center gap-1.5 text-[11px] text-muted">
          {!complete ? (
            <Loader2 size={11} className="animate-spin text-accent" />
          ) : failed ? (
            <AlertTriangle size={11} className="text-accent-deep" />
          ) : (
            <Check size={11} className="text-pine" />
          )}
          {complete ? `已完成 ${doneCount}/${steps.length} 步` : "Agent 正在执行"}
        </span>
        <ChevronDown
          size={13}
          className={["text-faint transition-transform", expanded ? "rotate-180" : ""].join(" ")}
        />
      </button>

      {expanded && (
        <ol className="border-t border-line/70 px-3 py-2">
          {steps.map((step, index) => (
            <li key={step.id} className="flex gap-2 py-[5px]">
              <span className="relative flex w-3.5 shrink-0 justify-center pt-[3px]">
                <StepIcon status={step.status} />
                {index < steps.length - 1 && (
                  <span className="absolute left-1/2 top-[17px] h-[calc(100%-8px)] w-px -translate-x-1/2 bg-line" />
                )}
              </span>
              <span className="min-w-0 flex-1">
                <span
                  className={[
                    "block text-[11.5px] leading-tight",
                    step.status === "running"
                      ? "text-ink"
                      : step.status === "failed"
                        ? "text-accent-deep"
                        : step.status === "pending"
                          ? "text-faint"
                          : "text-muted",
                  ].join(" ")}
                >
                  {step.label}
                </span>
                {step.detail && (
                  <span className="mt-0.5 block truncate text-[10.5px] text-faint">{step.detail}</span>
                )}
              </span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
