"use client";

import { clearSession, getToken } from "./auth";
import type { ImageFeatures, Product, User } from "./types";

export class ApiError extends Error {
  status: number;
  code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

type Detail = { code?: string; message?: string } | string | undefined;

function unpack(detail: Detail): { code: string; message: string } {
  if (typeof detail === "string") return { code: "ERROR", message: detail };
  if (detail && typeof detail === "object") {
    return { code: detail.code ?? "ERROR", message: detail.message ?? "请求失败" };
  }
  return { code: "ERROR", message: "请求失败" };
}

/** 统一带 token 的 fetch：401 直接清登录态，调用方只需要处理一次跳转。 */
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type") && init.body) headers.set("Content-Type", "application/json");
  if (token) {
    // 同时带两个头：Authorization 给本地/普通部署，X-Auth-Token 给会覆写 Authorization 的网关
    headers.set("Authorization", `Bearer ${token}`);
    headers.set("X-Auth-Token", token);
  }

  const res = await fetch(path, { ...init, headers, cache: "no-store" });

  if (res.status === 401) {
    clearSession();
    const body = await res.json().catch(() => ({}));
    const { code, message } = unpack(body?.detail);
    throw new ApiError(401, code, message);
  }

  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const { code, message } = unpack(data?.detail);
    throw new ApiError(res.status, code, message);
  }
  return data as T;
}

export type AuthResult = { token: string; expires_in: number; user: User };

export function login(user_id: string, password: string): Promise<AuthResult> {
  return api<AuthResult>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ user_id, password }),
  });
}

export function register(user_id: string, password: string, display_name?: string): Promise<AuthResult> {
  return api<AuthResult>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({ user_id, password, display_name }),
  });
}

export type ImageSearchResult = {
  ok: boolean;
  features: ImageFeatures;
  keywords: string[];
  products: Product[];
  mode: string;
  degraded: boolean;
  reason: string;
  elapsed_ms: number;
};

/** 拍图搜同款：图片在客户端压成 base64 再传，避免 multipart 与代理的兼容问题。 */
export function searchByImage(payload: {
  image_base64: string;
  mime: string;
  session_id: string;
  hint?: string;
  budget_max?: number;
}): Promise<ImageSearchResult> {
  return api<ImageSearchResult>("/api/search/image", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
