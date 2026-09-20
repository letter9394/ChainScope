import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ChainScope | Web3智能市场分析与风险预警平台",
  description: "Web3 intelligent market analysis with explainable cryptocurrency risk alerts.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
