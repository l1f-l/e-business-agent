"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowUp, ImagePlus, Loader2, Mic, MicOff, X } from "lucide-react";
import { compressImage, formatBytes } from "@/lib/image";
import { useDictation } from "@/lib/speech";

export type ImagePayload = {
  dataUrl: string;
  base64: string;
  mime: string;
  bytes: number;
};

type Props = {
  onSend: (text: string) => void;
  onSendImage: (image: ImagePayload, hint: string) => void;
  busy: boolean;
};

const SUGGESTIONS = [
  "500元以内降噪耳机",
  "查一下订单1001的物流",
  "3000以内的轻薄本有什么推荐",
  "想买个打游戏不卡的本子",
];

export default function Composer({ onSend, onSendImage, busy }: Props) {
  const [value, setValue] = useState("");
  const [image, setImage] = useState<ImagePayload | null>(null);
  const [reading, setReading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ref = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const imageRef = useRef<ImagePayload | null>(null);
  imageRef.current = image;

  const dictation = useDictation({
    onText: (text) => setValue(text),
    onFinal: (text) => {
      setValue(text);
      ref.current?.focus();
    },
  });

  useEffect(() => {
    if (dictation.error) setError(dictation.error);
  }, [dictation.error]);

  const resetHeight = () => {
    if (ref.current) ref.current.style.height = "auto";
  };

  const submit = () => {
    if (busy) return;
    const current = imageRef.current;
    if (current) {
      onSendImage(current, value.trim());
      setImage(null);
      setValue("");
      resetHeight();
      return;
    }
    const text = value.trim();
    if (!text) return;
    onSend(text);
    setValue("");
    resetHeight();
  };

  const pickFile = async (file: File | null | undefined) => {
    if (!file) return;
    setError(null);
    setReading(true);
    try {
      const compressed = await compressImage(file);
      setImage({
        dataUrl: compressed.dataUrl,
        base64: compressed.base64,
        mime: compressed.mime,
        bytes: compressed.bytes,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "图片读取失败");
    } finally {
      setReading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const onPaste = (event: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const file = Array.from(event.clipboardData.files).find((f) => f.type.startsWith("image/"));
    if (file) {
      event.preventDefault();
      void pickFile(file);
    }
  };

  const onDrop = (event: React.DragEvent<HTMLDivElement>) => {
    const file = Array.from(event.dataTransfer.files).find((f) => f.type.startsWith("image/"));
    if (file) {
      event.preventDefault();
      void pickFile(file);
    }
  };

  const canSend = Boolean(image) || value.trim().length > 0;

  return (
    <div
      className="border-t border-line bg-canvas/85 px-4 pb-4 pt-3 backdrop-blur sm:px-6"
      onDragOver={(e) => {
        if (e.dataTransfer.types.includes("Files")) e.preventDefault();
      }}
      onDrop={onDrop}
    >
      <div className="mx-auto w-full max-w-3xl">
        {!image && value.length === 0 && (
          <div className="no-scrollbar mb-2.5 flex gap-2 overflow-x-auto">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => onSend(s)}
                disabled={busy}
                className="shrink-0 rounded-full border border-line bg-white/70 px-3 py-1.5 text-[12px] text-muted transition hover:border-accent/40 hover:text-accent disabled:opacity-50"
              >
                {s}
              </button>
            ))}
          </div>
        )}

        {image && (
          <div className="mb-2 flex items-center gap-2.5 rounded-xl border border-line bg-white p-2">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={image.dataUrl} alt="待发送图片" className="h-14 w-14 rounded-lg object-cover" />
            <div className="min-w-0 flex-1">
              <p className="text-[12px] text-ink">按这张图搜同款</p>
              <p className="text-[10.5px] text-faint">
                已压缩到 {formatBytes(image.bytes)} · 可补充一句预算或用途
              </p>
            </div>
            <button
              type="button"
              onClick={() => setImage(null)}
              aria-label="移除图片"
              className="flex h-7 w-7 items-center justify-center rounded-full text-faint transition hover:bg-[#F4F1EA] hover:text-ink"
            >
              <X size={13} />
            </button>
          </div>
        )}

        {(error || dictation.error) && (
          <p className="mb-2 rounded-lg bg-[#FDF6EC] px-2.5 py-1.5 text-[11px] text-[#7A5416]">
            {error || dictation.error}
            <button
              type="button"
              className="ml-2 underline decoration-dotted"
              onClick={() => {
                setError(null);
                dictation.clearError();
              }}
            >
              知道了
            </button>
          </p>
        )}

        <div className="flex items-end gap-2 rounded-2xl border border-line bg-surface p-2 shadow-[0_1px_2px_rgba(27,27,24,0.04)] transition focus-within:border-accent/45 focus-within:shadow-[0_0_0_3px_rgba(194,74,43,0.08)]">
          <input
            ref={fileRef}
            type="file"
            accept="image/jpeg,image/png,image/webp,image/gif"
            className="hidden"
            onChange={(e) => void pickFile(e.target.files?.[0])}
          />
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            disabled={busy || reading}
            aria-label="上传图片搜同款"
            title="上传图片搜同款（也可以直接粘贴或拖进来）"
            className="mb-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-muted transition hover:bg-[#F4F1EA] hover:text-accent disabled:opacity-50"
          >
            {reading ? <Loader2 size={15} className="animate-spin" /> : <ImagePlus size={16} />}
          </button>

          {dictation.supported && (
            <button
              type="button"
              onClick={dictation.toggle}
              disabled={busy}
              aria-label={dictation.listening ? "停止语音输入" : "语音输入"}
              title={dictation.listening ? "正在听…再点一下停止" : "语音输入（中文）"}
              className={[
                "mb-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl transition disabled:opacity-50",
                dictation.listening
                  ? "bg-accent-soft text-accent"
                  : "text-muted hover:bg-[#F4F1EA] hover:text-accent",
              ].join(" ")}
            >
              {dictation.listening ? <MicOff size={16} className="animate-pulse" /> : <Mic size={16} />}
            </button>
          )}

          <textarea
            ref={ref}
            rows={1}
            value={value}
            disabled={busy}
            placeholder={
              dictation.listening
                ? "正在听你说话…"
                : image
                  ? "补一句预算或用途（可留空）…"
                  : "说说你的预算和用途，也可以粘贴图片搜同款…"
            }
            onChange={(e) => {
              setValue(e.target.value);
              const el = e.currentTarget;
              el.style.height = "auto";
              el.style.height = `${Math.min(el.scrollHeight, 132)}px`;
            }}
            onPaste={onPaste}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                submit();
              }
            }}
            className="max-h-[132px] min-h-[38px] flex-1 resize-none bg-transparent px-2 py-2 text-[14.5px] leading-relaxed text-ink outline-none placeholder:text-faint disabled:opacity-60"
          />

          <button
            type="button"
            onClick={submit}
            disabled={busy || !canSend}
            aria-label="发送"
            className="mb-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-accent text-white transition hover:bg-accent-deep disabled:cursor-not-allowed disabled:bg-[#DCD7CE]"
          >
            {busy ? <Loader2 size={16} className="animate-spin" /> : <ArrowUp size={17} />}
          </button>
        </div>

        <p className="mt-2 text-center text-[10.5px] text-faint">
          Enter 发送 · Shift + Enter 换行 · 支持粘贴/拖拽图片 · 商品与订单均为模拟数据
        </p>
      </div>
    </div>
  );
}
