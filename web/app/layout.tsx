import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ChainScope | Crypto Risk Intelligence",
  description: "Explainable cryptocurrency market risk analysis.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
