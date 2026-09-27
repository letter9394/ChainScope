import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";

import { chromium } from "@playwright/test";

const baseUrl = process.env.PORTFOLIO_URL ?? "https://chainscope-web3.onrender.com/";
const outputDir = resolve(process.cwd(), "../docs/assets");

await mkdir(outputDir, { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({
  viewport: { width: 1440, height: 1000 },
  deviceScaleFactor: 1,
});

try {
  await page.goto(baseUrl, { waitUntil: "domcontentloaded", timeout: 120_000 });
  await page.getByLabel("核心资产行情").waitFor({ state: "visible", timeout: 120_000 });
  await page.waitForTimeout(8_000);

  const marketGrid = page.getByLabel("核心资产行情");
  await marketGrid.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: resolve(outputDir, "dashboard-overview.png"),
    animations: "disabled",
  });

  const dashboard = page.locator(".dashboard-grid");
  await dashboard.scrollIntoViewIfNeeded();
  await dashboard.screenshot({
    path: resolve(outputDir, "candlestick-risk.png"),
    animations: "disabled",
  });

  const derivatives = page.locator(".derivatives-section");
  await derivatives.scrollIntoViewIfNeeded();
  await derivatives.screenshot({
    path: resolve(outputDir, "derivatives-risk.png"),
    animations: "disabled",
  });

  const backtest = page.locator("#risk-backtest");
  await backtest.waitFor({ state: "visible", timeout: 120_000 });
  await backtest.scrollIntoViewIfNeeded();
  await backtest.screenshot({
    path: resolve(outputDir, "risk-backtest.png"),
    animations: "disabled",
  });

  console.log(`Portfolio screenshots saved to ${outputDir}`);
} finally {
  await browser.close();
}
