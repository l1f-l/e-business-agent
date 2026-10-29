import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ShopPilot · AI 导购与客服",
  description:
    "基于 DeepSeek 的电商智能导购与客服 Agent：商品 RAG 推荐 + 订单查询 Function Calling",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body className="min-h-screen bg-canvas font-sans text-ink antialiased">{children}</body>
    </html>
  );
}
