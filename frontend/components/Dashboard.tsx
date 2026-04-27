"use client";

import { useMemo, useState } from "react";
import { TICKERS, Ticker } from "@/lib/types";
import { useStreamSocket } from "@/hooks/useStreamSocket";
import Sidebar from "./Sidebar";
import KpiCard from "./KpiCard";
import PriceChart from "./PriceChart";
import StatusBadge from "./StatusBadge";

const BRIDGE_URL =
  process.env.NEXT_PUBLIC_BRIDGE_WS ?? "ws://127.0.0.1:8765/ws";

const fmt = (n: number | undefined, d = 2) =>
  n === undefined || Number.isNaN(n) ? "—" : n.toFixed(d);

export default function Dashboard() {
  const { series, conn } = useStreamSocket(BRIDGE_URL);
  const [selected, setSelected] = useState<Ticker>("AAPL");

  // Per-symbol summaries used by the sidebar.
  const lastPrices = useMemo(() => {
    const out: Record<string, number | undefined> = {};
    for (const t of TICKERS) {
      const arr = series[t];
      out[t] = arr && arr.length ? arr[arr.length - 1].close : undefined;
    }
    return out;
  }, [series]);

  const counts = useMemo(() => {
    const out: Record<string, number | undefined> = {};
    for (const t of TICKERS) out[t] = series[t]?.length;
    return out;
  }, [series]);

  const data = series[selected] ?? [];
  const latest = data.length ? data[data.length - 1] : undefined;
  const prev   = data.length > 1 ? data[data.length - 2] : undefined;

  const change   = latest && prev ? latest.close - prev.close : 0;
  const changePc = latest && prev && prev.close ? (change / prev.close) * 100 : 0;

  const tone: "up" | "down" | "neutral" =
    change > 0 ? "up" : change < 0 ? "down" : "neutral";

  return (
    <div className="h-screen w-screen flex flex-col bg-terminal-bg text-terminal-text overflow-hidden">
      {/* Top bar */}
      <header className="h-12 border-b border-terminal-border bg-terminal-panel flex items-center justify-between px-4">
        <div className="flex items-center gap-3">
          <div className="text-terminal-accent font-bold tracking-widest text-sm">FINNHUB · TERMINAL</div>
          <div className="text-terminal-dim text-[11px]">EMA crossover · Welford variance · live</div>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-[11px] text-terminal-dim">
            {Object.keys(series).length} / {TICKERS.length} streaming
          </span>
          <StatusBadge state={conn} />
        </div>
      </header>

      <div className="flex-1 flex min-h-0">
        <Sidebar
          selected={selected}
          onSelect={setSelected}
          lastPrices={lastPrices}
          counts={counts}
        />

        <main className="flex-1 flex flex-col min-w-0">
          {/* Symbol header */}
          <div className="px-6 py-4 border-b border-terminal-border flex items-end justify-between">
            <div>
              <div className="text-[10px] uppercase tracking-widest text-terminal-dim">Symbol</div>
              <div className="flex items-baseline gap-3">
                <h1 className="text-3xl font-semibold tracking-wide">{selected}</h1>
                <span className={`text-sm tabular-nums ${
                  tone === "up" ? "text-terminal-green" :
                  tone === "down" ? "text-terminal-red" : "text-terminal-dim"
                }`}>
                  {latest ? fmt(latest.close) : "—"}
                  {prev && (
                    <span className="ml-3">
                      {change >= 0 ? "+" : ""}{fmt(change, 4)} ({changePc >= 0 ? "+" : ""}{fmt(changePc, 3)}%)
                    </span>
                  )}
                </span>
              </div>
            </div>
            <div className="text-[11px] text-terminal-dim tabular-nums">
              {latest?.now ? `last update: ${latest.now}` : "no data yet"}
            </div>
          </div>

          {/* KPI row */}
          <div className="px-6 py-4 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            <KpiCard label="Close"      value={fmt(latest?.close)}   tone={tone} />
            <KpiCard label="EMA 10m"    value={fmt(latest?.ema10)}   sub={`Δ vs close ${fmt(latest && (latest.close - latest.ema10), 4)}`} />
            <KpiCard label="EMA 50m"    value={fmt(latest?.ema50)}   sub={`Δ vs close ${fmt(latest && (latest.close - latest.ema50), 4)}`} />
            <KpiCard label="Min / Max"  value={`${fmt(latest?.min10)} – ${fmt(latest?.max10)}`} sub={`range ${fmt(latest && (latest.max10 - latest.min10), 4)}`} />
            <KpiCard label="Var 10m"    value={fmt(latest?.var10, 6)} tone="warn" />
            <KpiCard label="Var 50m"    value={fmt(latest?.var50, 6)} sub={`n=${latest?.count50 ?? 0}`} tone="warn" />
          </div>

          {/* Chart */}
          <div className="flex-1 min-h-0 px-6 pb-6 flex flex-col">
            <div className="flex-1 min-h-0 bg-terminal-panel border border-terminal-border rounded-md shadow-panel flex flex-col overflow-hidden">
              <div className="px-4 py-2 border-b border-terminal-border flex items-center justify-between text-[11px] text-terminal-dim">
                <span>Price · EMA10 · EMA50</span>
                <span className="tabular-nums">{data.length} pts</span>
              </div>
              <PriceChart data={data} symbol={selected} />
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
