"use client";

import { useEffect, useRef, useState } from "react";
import { HISTORY_LIMIT, Tick } from "@/lib/types";

type ConnState = "connecting" | "open" | "closed";

type SeriesMap = Record<string, Tick[]>;

// Append-and-cap: keeps the per-symbol series at HISTORY_LIMIT entries.
function appendCapped(prev: Tick[], next: Tick): Tick[] {
  // The bridge can deliver out-of-order blocks if the producer ever rewrites;
  // keep them sorted by ts so the chart never zig-zags backward.
  const out = prev.length && next.ts < prev[prev.length - 1].ts
    ? [...prev, next].sort((a, b) => a.ts - b.ts)
    : [...prev, next];
  return out.length > HISTORY_LIMIT ? out.slice(out.length - HISTORY_LIMIT) : out;
}

/**
 * Maintains a single WebSocket connection to the bridge and exposes a
 * per-symbol sliding window of ticks. Reconnects with backoff on drop.
 */
export function useStreamSocket(url: string) {
  const [series, setSeries] = useState<SeriesMap>({});
  const [conn, setConn]     = useState<ConnState>("connecting");

  // Mutable refs so reconnect logic doesn't churn React state.
  const wsRef       = useRef<WebSocket | null>(null);
  const retryRef    = useRef(0);
  const cancelledRef = useRef(false);

  useEffect(() => {
    cancelledRef.current = false;

    const connect = () => {
      if (cancelledRef.current) return;
      setConn("connecting");

      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        retryRef.current = 0;
        setConn("open");
      };

      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          if (msg.type === "snapshot") {
            // Replace state in one shot; snapshot already capped server-side.
            const snap = msg.data as SeriesMap;
            const capped: SeriesMap = {};
            for (const [sym, arr] of Object.entries(snap)) {
              capped[sym] = arr.slice(-HISTORY_LIMIT);
            }
            setSeries(capped);
          } else if (msg.type === "tick") {
            const tick = msg.data as Tick;
            setSeries((prev) => ({
              ...prev,
              [tick.symbol]: appendCapped(prev[tick.symbol] ?? [], tick),
            }));
          }
        } catch {
          // ignore malformed frames
        }
      };

      ws.onclose = () => {
        setConn("closed");
        if (cancelledRef.current) return;
        // exponential backoff capped at 5s
        const delay = Math.min(5000, 250 * Math.pow(2, retryRef.current++));
        setTimeout(connect, delay);
      };

      ws.onerror = () => ws.close();
    };

    connect();

    return () => {
      cancelledRef.current = true;
      wsRef.current?.close();
    };
  }, [url]);

  return { series, conn };
}
