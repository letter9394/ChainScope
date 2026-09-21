"use client";

import { useEffect, useState } from "react";
import type { Dispatch, SetStateAction } from "react";

import type { MarketCoin } from "@/lib/types";

export type LiveMarketStatus = "connecting" | "live" | "fallback";

const symbolToAsset: Record<string, string> = {
  BTCUSDT: "bitcoin",
  ETHUSDT: "ethereum",
  SOLUSDT: "solana",
};

const streamNames = Object.keys(symbolToAsset)
  .map((symbol) => `${symbol.toLowerCase()}@ticker`)
  .join("/");

const streamUrl = `wss://stream.binance.com:9443/stream?streams=${streamNames}`;

interface BinanceTicker {
  E?: number;
  P?: string;
  c?: string;
  s?: string;
}

interface BinanceStreamEvent {
  data?: BinanceTicker;
}

export function useLiveCryptoPrices(
  setMarkets: Dispatch<SetStateAction<MarketCoin[]>>,
): LiveMarketStatus {
  const [status, setStatus] = useState<LiveMarketStatus>("connecting");

  useEffect(() => {
    let socket: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let stopped = false;

    const connect = () => {
      if (stopped) return;
      setStatus("connecting");
      socket = new WebSocket(streamUrl);

      socket.onopen = () => setStatus("live");
      socket.onmessage = (event) => {
        try {
          const payload = (JSON.parse(event.data) as BinanceStreamEvent).data;
          const assetId = payload?.s ? symbolToAsset[payload.s] : undefined;
          const price = Number(payload?.c);
          const change = Number(payload?.P);
          if (!assetId || !Number.isFinite(price) || !Number.isFinite(change)) return;

          setMarkets((current) => current.map((market) => market.id === assetId
            ? {
                ...market,
                current_price: price,
                price_change_percentage_24h: change,
                last_updated: payload?.E ? new Date(payload.E).toISOString() : market.last_updated,
              }
            : market));
        } catch {
          // Ignore malformed frames and keep the last valid quote on screen.
        }
      };
      socket.onerror = () => socket?.close();
      socket.onclose = () => {
        if (stopped) return;
        setStatus("fallback");
        reconnectTimer = window.setTimeout(connect, 5_000);
      };
    };

    connect();
    return () => {
      stopped = true;
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, [setMarkets]);

  return status;
}
