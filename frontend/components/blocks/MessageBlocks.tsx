"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { AlertCircle, Check, Loader2, Volume2, VolumeX, Wrench } from "lucide-react";
import { useSpeak } from "@/lib/speech";
import type { Block, ChatMessage } from "@/lib/types";
import PlanProgress from "./PlanProgress";
import ProductRow from "./ProductRow";
import CompareCard from "./CompareCard";
import ReviewSummaryBlock from "./ReviewSummary";
import OrderCard from "./OrderCard";
import RefundCard from "./RefundCard";
import ImageMatchCard from "./ImageMatchCard";
import SuggestCard from "./SuggestCard";

function Markdown({ text }: { text: string }) {
  return (
    <div className="text-[15px] leading-[1.78] text-ink/90 [word-break:break-word]">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }: { children?: React.ReactNode }) => (
            <p className="mb-2 last:mb-0">{children}</p>
          ),
          ul: ({ children }: { children?: React.ReactNode }) => (
            <ul className="mb-2 list-disc space-y-1 pl-5 last:mb-0">{children}</ul>
          ),
          ol: ({ children }: { children?: React.ReactNode }) => (
            <ol className="mb-2 list-decimal space-y-1 pl-5 last:mb-0">{children}</ol>
          ),
          li: ({ children }: { children?: React.ReactNode }) => <li className="pl-0.5">{children}</li>,
          strong: ({ children }: { children?: React.ReactNode }) => (
            <strong className="font-medium text-ink">{children}</strong>
          ),
          code: ({ children }: { children?: React.ReactNode }) => (
            <code className="rounded bg-[#F1EFE8] px-1 py-0.5 font-mono text-[13px]">{children}</code>
          ),
          a: ({ children }: { children?: React.ReactNode }) => (
            <span className="text-accent underline decoration-accent/30">{children}</span>
          ),
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}

function ToolChip({ block, streaming }: { block: Extract<Block, { kind: "tool" }>; streaming?: boolean }) {
  return (
    <span
      className={[
        "inline-flex items-center gap-1 rounded-full border px-2 py-[3px] text-[10.5px]",
        block.ok ? "border-[#D6E6D8] bg-[#F2F7F1] text-pine" : "border-[#F0DCC8] bg-[#FDF6EC] text-[#A9701B]",
      ].join(" ")}
    >
      {streaming ? <Loader2 size={10} className="animate-spin" /> : block.ok ? <Check size={10} /> : <Wrench size={10} />}
      <span className="font-mono">{block.label}</span>
    </span>
  );
}

function renderBlock(block: Block, index: number, streaming?: boolean, onAsk?: (text: string) => void) {
  switch (block.kind) {
    case "plan":
      return <PlanProgress key={index} steps={block.steps} />;
    case "match":
      return <ImageMatchCard key={index} features={block.features} degraded={block.degraded} />;
    case "suggest":
      return <SuggestCard key={index} data={block.data} onAsk={onAsk} />;
    case "text":
      return <Markdown key={index} text={block.text} />;
    case "products":
      return <ProductRow key={index} items={block.items} />;
    case "reviews":
      return <ReviewSummaryBlock key={index} summaries={block.summaries} />;
    case "compare":
      return <CompareCard key={index} data={block.data} />;
    case "order":
      return <OrderCard key={index} order={block.data} />;
    case "refund":
      return <RefundCard key={index} data={block.data} />;
    case "tool":
      return (
        <span key={index} className="mb-2 mr-1.5 inline-flex">
          <ToolChip block={block} streaming={streaming} />
        </span>
      );
    default:
      return null;
  }
}

type Props = {
  message: ChatMessage;
  onAsk?: (text: string) => void;
};

export default function MessageBlocks({ message, onAsk }: Props) {
  const toolBlocks = message.blocks.filter((b): b is Extract<Block, { kind: "tool" }> => b.kind === "tool");
  const otherBlocks = message.blocks.filter((b) => b.kind !== "tool");
  const plainText = message.blocks
    .filter((b): b is Extract<Block, { kind: "text" }> => b.kind === "text")
    .map((b) => b.text)
    .join("\n");
  const { supported: canSpeak, speakingId, toggle } = useSpeak();
  const speaking = speakingId === message.id;

  return (
    <div className="space-y-0.5">
      {toolBlocks.length > 0 && (
        <div className="mb-2 flex flex-wrap items-center gap-1.5">
          {toolBlocks.map((block, index) => (
            <ToolChip key={index} block={block} streaming={false} />
          ))}
        </div>
      )}

      {otherBlocks.map((block, index) => renderBlock(block, index, message.streaming, onAsk))}

      {message.streaming && (
        <span className="caret ml-0.5 inline-block h-[13px] w-[2px] translate-y-[2px] bg-ink/50 align-middle" />
      )}

      {!message.streaming && canSpeak && plainText.trim().length > 0 && (
        <button
          type="button"
          onClick={() => toggle(message.id, plainText)}
          aria-label={speaking ? "停止朗读" : "朗读这条回复"}
          className="mt-1.5 inline-flex items-center gap-1 rounded-full border border-line bg-white px-2 py-[3px] text-[10.5px] text-faint transition hover:border-accent/40 hover:text-accent"
        >
          {speaking ? <VolumeX size={10} /> : <Volume2 size={10} />}
          {speaking ? "停止" : "朗读"}
        </button>
      )}

      {message.error && (
        <div className="mt-2 flex items-start gap-2 rounded-xl border border-[#F0DCC8] bg-[#FDF6EC] px-3 py-2">
          <AlertCircle size={14} className="mt-0.5 shrink-0 text-[#A9701B]" />
          <p className="text-[11.5px] leading-relaxed text-[#7A5416]">{message.error}</p>
        </div>
      )}
    </div>
  );
}
