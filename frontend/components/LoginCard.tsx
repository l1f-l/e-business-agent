"use client";

import { useState } from "react";
import { ArrowRight, KeyRound, Loader2, ShieldCheck, ShoppingBag } from "lucide-react";
import { ApiError, login, register, type AuthResult } from "@/lib/api";

type Props = {
  onLogin: (result: AuthResult) => void;
};

const DEMO = [
  { user_id: "u1001", name: "林一", note: "订单 1001 / 1002" },
  { user_id: "u1002", name: "周一鸣", note: "订单 1003（已签收）" },
  { user_id: "u1003", name: "苏晴", note: "订单 1004 / 1005" },
  { user_id: "u1004", name: "陈默", note: "订单 1006（已取消）" },
];

export default function LoginCard({ onLogin }: Props) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [userId, setUserId] = useState("u1001");
  const [password, setPassword] = useState("shop1234");
  const [displayName, setDisplayName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const result =
        mode === "login"
          ? await login(userId.trim(), password)
          : await register(userId.trim(), password, displayName.trim() || undefined);
      onLogin(result);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "网络异常，请稍后重试");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-10">
      <div className="w-full max-w-[880px] overflow-hidden rounded-3xl border border-line bg-surface shadow-[0_18px_60px_-30px_rgba(27,27,24,0.35)] md:grid md:grid-cols-[1.05fr_1fr]">
        <aside className="hidden flex-col justify-between bg-[#F2EFE8] p-9 md:flex">
          <div>
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-ink text-[12px] font-medium text-white">
              SP
            </div>
            <h1 className="mt-6 text-[22px] font-medium leading-tight tracking-tight text-ink">
              ShopPilot
              <span className="mt-1 block text-[13px] font-normal text-muted">电商 AI 导购与客服 Agent</span>
            </h1>
            <p className="mt-4 text-[12.5px] leading-relaxed text-muted">
              双路 RAG 检索商品与真实评论，Function Calling 完成查单、加购、退款。所有数据都绑定在你自己的账号下。
            </p>
          </div>

          <ul className="mt-8 space-y-2.5 text-[12px] text-muted">
            <li className="flex items-center gap-2">
              <ShieldCheck size={13} className="text-pine" />
              JWT 鉴权 · 订单与购物车按用户隔离
            </li>
            <li className="flex items-center gap-2">
              <ShoppingBag size={13} className="text-accent" />
              加购后右侧抽屉实时同步
            </li>
            <li className="flex items-center gap-2">
              <KeyRound size={13} className="text-faint" />
              demo 账号密码统一为 shop1234
            </li>
          </ul>
        </aside>

        <section className="p-7 sm:p-9">
          <div className="mb-5 flex gap-1 rounded-full bg-[#F3F0E9] p-1 text-[12px]">
            {(["login", "register"] as const).map((key) => (
              <button
                key={key}
                type="button"
                onClick={() => {
                  setMode(key);
                  setError(null);
                }}
                className={[
                  "flex-1 rounded-full py-1.5 transition",
                  mode === key ? "bg-white text-ink shadow-sm" : "text-muted hover:text-ink",
                ].join(" ")}
              >
                {key === "login" ? "登录" : "注册新账号"}
              </button>
            ))}
          </div>

          <form onSubmit={submit} className="space-y-3">
            <label className="block">
              <span className="text-[11px] text-faint">user_id</span>
              <input
                value={userId}
                onChange={(e) => setUserId(e.target.value)}
                autoComplete="username"
                placeholder="例如 u1001"
                className="mt-1 w-full rounded-xl border border-line bg-white px-3 py-2.5 text-[13.5px] text-ink outline-none transition focus:border-accent/50 focus:ring-2 focus:ring-accent/10"
              />
            </label>

            {mode === "register" && (
              <label className="block">
                <span className="text-[11px] text-faint">昵称（可选）</span>
                <input
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="显示在对话里的名字"
                  className="mt-1 w-full rounded-xl border border-line bg-white px-3 py-2.5 text-[13.5px] text-ink outline-none transition focus:border-accent/50 focus:ring-2 focus:ring-accent/10"
                />
              </label>
            )}

            <label className="block">
              <span className="text-[11px] text-faint">密码</span>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                placeholder="至少 6 位"
                className="mt-1 w-full rounded-xl border border-line bg-white px-3 py-2.5 text-[13.5px] text-ink outline-none transition focus:border-accent/50 focus:ring-2 focus:ring-accent/10"
              />
            </label>

            {error && (
              <p className="rounded-lg bg-accent-soft px-3 py-2 text-[12px] text-accent-deep">{error}</p>
            )}

            <button
              type="submit"
              disabled={busy || !userId.trim() || !password}
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-accent py-2.5 text-[13.5px] font-medium text-white transition hover:bg-accent-deep disabled:cursor-not-allowed disabled:bg-[#DCD7CE]"
            >
              {busy ? <Loader2 size={15} className="animate-spin" /> : <ArrowRight size={15} />}
              {mode === "login" ? "进入商城" : "注册并进入"}
            </button>
          </form>

          <div className="mt-6">
            <p className="text-[10.5px] uppercase tracking-[0.08em] text-faint">demo 账号 · 点击填入</p>
            <div className="mt-2 grid gap-1.5 sm:grid-cols-2">
              {DEMO.map((item) => (
                <button
                  key={item.user_id}
                  type="button"
                  onClick={() => {
                    setMode("login");
                    setUserId(item.user_id);
                    setPassword("shop1234");
                    setError(null);
                  }}
                  className="rounded-xl border border-line bg-white px-3 py-2 text-left transition hover:border-accent/40"
                >
                  <span className="flex items-center justify-between text-[12px] text-ink">
                    {item.name}
                    <span className="font-mono text-[10px] text-faint">{item.user_id}</span>
                  </span>
                  <span className="mt-0.5 block text-[10px] text-faint">{item.note}</span>
                </button>
              ))}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
