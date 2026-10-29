"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/* ---------------- Web Speech API 的最小类型 ---------------- */

type RecognitionResult = {
  resultIndex: number;
  results: ArrayLike<{ isFinal: boolean; length: number; 0: { transcript: string } }>;
};

type Recognition = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((event: RecognitionResult) => void) | null;
  onerror: ((event: { error?: string }) => void) | null;
  onend: (() => void) | null;
  onstart: (() => void) | null;
};

function recognitionCtor(): (new () => Recognition) | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    SpeechRecognition?: new () => Recognition;
    webkitSpeechRecognition?: new () => Recognition;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export function speechSupported(): boolean {
  return recognitionCtor() !== null;
}

export function synthesisSupported(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

const ERROR_TEXT: Record<string, string> = {
  "not-allowed": "麦克风权限被拒绝，请在地址栏左侧的权限设置里允许后重试。",
  "service-not-allowed": "浏览器禁用了语音识别服务。",
  network: "语音识别服务连不上（Chrome 的识别走境外服务），先用键盘输入吧。",
  "no-speech": "没听到声音，再说一次？",
  "audio-capture": "没有检测到麦克风设备。",
  aborted: "",
};

/* ---------------- 语音输入 ---------------- */

export function useDictation(handler: { onText?: (text: string) => void; onFinal?: (text: string) => void }) {
  const [listening, setListening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const recognitionRef = useRef<Recognition | null>(null);
  const bufferRef = useRef("");
  const handlerRef = useRef(handler);
  handlerRef.current = handler;

  useEffect(() => () => recognitionRef.current?.abort(), []);

  const stop = useCallback(() => {
    recognitionRef.current?.stop();
    setListening(false);
  }, []);

  const start = useCallback(() => {
    const Ctor = recognitionCtor();
    if (!Ctor) {
      setError("当前浏览器不支持语音输入，建议用 Chrome 或 Edge。");
      return;
    }
    setError(null);
    bufferRef.current = "";

    const recognition = new Ctor();
    recognition.lang = "zh-CN";
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => setListening(true);
    recognition.onresult = (event) => {
      let text = "";
      for (let i = 0; i < event.results.length; i += 1) {
        text += event.results[i][0]?.transcript ?? "";
      }
      bufferRef.current = text;
      handlerRef.current.onText?.(text);
    };
    recognition.onerror = (event) => {
      const message = ERROR_TEXT[event.error ?? ""] ?? "语音识别失败，请重试。";
      if (message) setError(message);
      setListening(false);
    };
    recognition.onend = () => {
      setListening(false);
      const text = bufferRef.current.trim();
      if (text) handlerRef.current.onFinal?.(text);
    };

    recognitionRef.current = recognition;
    try {
      recognition.start();
    } catch {
      setError("麦克风启动失败，可能已经在录音中。");
    }
  }, []);

  const toggle = useCallback(() => {
    if (listening) stop();
    else start();
  }, [listening, start, stop]);

  return { supported: speechSupported(), listening, error, start, stop, toggle, clearError: () => setError(null) };
}

/* ---------------- 朗读 ---------------- */

export function useSpeak() {
  const [speakingId, setSpeakingId] = useState<string | null>(null);

  useEffect(() => () => {
    if (synthesisSupported()) window.speechSynthesis.cancel();
  }, []);

  const stop = useCallback(() => {
    if (synthesisSupported()) window.speechSynthesis.cancel();
    setSpeakingId(null);
  }, []);

  const toggle = useCallback(
    (id: string, text: string) => {
      if (!synthesisSupported()) return;
      if (speakingId === id) {
        stop();
        return;
      }
      const clean = text
        .replace(/[#*`>_~]/g, " ")
        .replace(/\s+/g, " ")
        .trim();
      if (!clean) return;

      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(clean.slice(0, 800));
      const voice = window.speechSynthesis.getVoices().find((v) => /zh|Chinese/i.test(v.lang));
      if (voice) utterance.voice = voice;
      utterance.lang = voice?.lang ?? "zh-CN";
      utterance.rate = 1.05;
      utterance.onend = () => setSpeakingId(null);
      utterance.onerror = () => setSpeakingId(null);
      setSpeakingId(id);
      window.speechSynthesis.speak(utterance);
    },
    [speakingId, stop],
  );

  return { supported: synthesisSupported(), speakingId, toggle, stop };
}
