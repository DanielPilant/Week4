"use client";

import { useMemo } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Tick } from "@/lib/types";

type Props = { data: Tick[]; symbol: string };

const fmtTime = (ms: number) => {
  const d = new Date(ms);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
};

const fmtPrice = (n: number) => n.toFixed(2);

/**
 * Live price chart with EMA10 / EMA50 overlay.
 * Y-axis auto-scales to the visible window; padding added so lines don't
 * touch the edges of the plot area.
 */
export default function PriceChart({ data, symbol }: Props) {
  const { domain, ticks } = useMemo(() => {
    if (data.length === 0) {
      return { domain: ["auto", "auto"] as [string | number, string | number], ticks: [] as number[] };
    }
    let lo = Infinity, hi = -Infinity;
    for (const d of data) {
      lo = Math.min(lo, d.close, d.ema10, d.ema50);
      hi = Math.max(hi, d.close, d.ema10, d.ema50);
    }
    const pad = Math.max((hi - lo) * 0.08, hi * 0.0005);
    return {
      domain: [lo - pad, hi + pad] as [number, number],
      ticks: data.length > 8
        ? data.filter((_, i) => i % Math.ceil(data.length / 6) === 0).map((d) => d.ts)
        : data.map((d) => d.ts),
    };
  }, [data]);

  if (data.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-terminal-dim text-sm">
        Waiting for stream data for <span className="text-terminal-text mx-1">{symbol}</span>…
      </div>
    );
  }

  return (
    <div className="flex-1 min-h-0">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 16, right: 24, left: 8, bottom: 8 }}>
          <CartesianGrid stroke="#1c2530" strokeDasharray="2 4" vertical={false} />
          <XAxis
            dataKey="ts"
            type="number"
            domain={["dataMin", "dataMax"]}
            ticks={ticks}
            tickFormatter={fmtTime}
            stroke="#5c6773"
            tick={{ fill: "#5c6773", fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: "#1c2530" }}
          />
          <YAxis
            domain={domain}
            tickFormatter={fmtPrice}
            stroke="#5c6773"
            tick={{ fill: "#5c6773", fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: "#1c2530" }}
            width={64}
          />
          <Tooltip
            labelFormatter={(v) => fmtTime(Number(v))}
            formatter={(v: number, name) => [fmtPrice(v), name]}
            cursor={{ stroke: "#1c2530", strokeWidth: 1 }}
          />
          <Legend
            verticalAlign="top"
            height={28}
            iconType="plainline"
            wrapperStyle={{ fontSize: 11, color: "#5c6773" }}
          />
          <Line
            type="monotone"
            dataKey="close"
            name="Close"
            stroke="#d3d8e0"
            strokeWidth={1.75}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="ema10"
            name="EMA 10m"
            stroke="#39bae6"
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="ema50"
            name="EMA 50m"
            stroke="#ffb454"
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
