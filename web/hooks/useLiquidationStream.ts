"use client";

import { useEffect, useState } from "react";

export type LiquidationStatus = "connecting" | "live" | "offline" | "unsupported";

export interface LiquidationStats {
  status: LiquidationStatus;
  totalUsd: number;
  longUsd: number;
  shortUsd: number;
  lastEventAt: string | null;
}

const assetSymbols: Record<string, string> = {
  bitcoin: "btcusdt",
  ethereum: "ethusdt",
  solana: "solusdt",
};

interface ForceOrderPayload {
  o?: {
    S?: "BUY" | "SELL";
    ap?: string;
    p?: string;
    q?: string;
    T?: number;
  };
}

interface LiquidationEvent {
  timestamp: number;
  side: "long" | "short";
  notional: number;
}

const emptyStats = (status: LiquidationStatus): LiquidationStats => ({
  status,
  totalUsd: 0,
  longUsd: 0,
  shortUsd: 0,
  lastEventAt: null,
});

export function useLiquidationStream(assetId: string): LiquidationStats {
  const [stats, setStats] = useState<LiquidationStats>(() => emptyStats("connecting"));

  useEffect(() => {
    const symbol = assetSymbols[assetId];
    if (!symbol) {
      setStats(emptyStats("unsupported"));
      return;
    }

    let socket: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let stopped = false;
    let events: LiquidationEvent[] = [];
    let lastEventAt: string | null = null;

    const publish = (status: LiquidationStatus, eventTime?: number) => {
      const cutoff = Date.now() - 5 * 60_000;
      events = events.filter((event) => event.timestamp >= cutoff);
      const longUsd = events.filter((event) => event.side === "long").reduce((sum, event) => sum + event.notional, 0);
      const shortUsd = events.filter((event) => event.side === "short").reduce((sum, event) => sum + event.notional, 0);
      if (eventTime) lastEventAt = new Date(eventTime).toISOString();
      setStats({
        status,
        totalUsd: longUsd + shortUsd,
        longUsd,
        shortUsd,
        lastEventAt,
      });
    };

    const connect = () => {
      if (stopped) return;
      publish("connecting");
      socket = new WebSocket(`wss://fstream.binance.com/ws/${symbol}@forceOrder`);
      socket.onopen = () => publish("live");
      socket.onmessage = (message) => {
        try {
          const order = (JSON.parse(message.data) as ForceOrderPayload).o;
          const price = Number(order?.ap || order?.p);
          const quantity = Number(order?.q);
          const timestamp = order?.T ?? Date.now();
          if (!order?.S || !Number.isFinite(price) || !Number.isFinite(quantity)) return;
          events.push({
            timestamp,
            side: order.S === "SELL" ? "long" : "short",
            notional: price * quantity,
          });
          publish("live", timestamp);
        } catch {
          // Keep the last valid statistics when a malformed frame arrives.
        }
      };
      socket.onerror = () => socket?.close();
      socket.onclose = () => {
        if (stopped) return;
        publish("offline");
        reconnectTimer = window.setTimeout(connect, 5_000);
      };
    };

    connect();
    const pruneTimer = window.setInterval(() => publish(socket?.readyState === WebSocket.OPEN ? "live" : "offline"), 15_000);
    return () => {
      stopped = true;
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
      window.clearInterval(pruneTimer);
      socket?.close();
    };
  }, [assetId]);

  return stats;
}
