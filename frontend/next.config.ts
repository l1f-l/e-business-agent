import type { NextConfig } from "next";

/**
 * 两种构建形态：
 * - 开发 / 内网演示（不设 STATIC_EXPORT）：`next dev` 照旧，`app/api/*` 作为后端代理
 * - 线上单端口（STATIC_EXPORT=1）：产出纯静态 out/，和 FastAPI 同源托管；
 *   此时 /api/* 直接命中 FastAPI，不需要任何 Node 侧代理
 *   （构建脚本会临时把 app/api 移出去，静态导出不允许存在 route handler）
 */
const isStatic = process.env.STATIC_EXPORT === "1";

const nextConfig: NextConfig = {
  poweredByHeader: false,
  ...(isStatic
    ? {
        output: "export" as const,
        images: { unoptimized: true },
        // Windows 上 /404 与 /_not-found 会并发写同一个 404.html（EPERM），
        // 把静态导出的并发降到 1 即可避免；页面本来就只有几个，速度无影响。
        experimental: { staticGenerationMaxConcurrency: 1 },
      }
    : {}),
};

export default nextConfig;
