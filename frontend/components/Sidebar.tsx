"use client";

import { TICKERS, Ticker } from "@/lib/types";

type Props = {
  selected:    Ticker;
  onSelect:    (t: Ticker) => void;
  lastPrices:  Record<string, number | undefined>;
  counts:      Record<string, number | undefined>;
};

/** Left rail: ticker selector with live last-price preview. */
export default function Sidebar({ selected, onSelect, lastPrices, counts }: Props) {
  return (
    <aside className="w-56 shrink-0 bg-terminal-panel border-r border-terminal-border flex flex-col">
      <div className="px-4 py-3 border-b border-terminal-border">
        <div className="text-[10px] uppercase tracking-widest text-terminal-dim">Watchlist</div>
        <div className="text-sm text-terminal-text mt-0.5">Tech & ETFs</div>
      </div>

      <nav className="flex-1 overflow-y-auto py-1">
        {TICKERS.map((t) => {
          const price = lastPrices[t];
          const isActive = t === selected;
          return (
            <button
              key={t}
              onClick={() => onSelect(t)}
              className={[
                "w-full text-left px-4 py-2 flex items-center justify-between",
                "border-l-2 transition-colors text-xs",
                isActive
                  ? "border-terminal-accent bg-black/30 text-terminal-text"
                  : "border-transparent hover:bg-black/20 text-terminal-dim hover:text-terminal-text",
              ].join(" ")}
            >
              <span className="font-semibold tracking-wide">{t}</span>
              <span className="tabular-nums text-right">
                {price !== undefined ? price.toFixed(2) : <span className="text-terminal-dim">—</span>}
                <span className="block text-[9px] text-terminal-dim">
                  {counts[t] ? `${counts[t]} pts` : "no data"}
                </span>
              </span>
            </button>
          );
        })}
      </nav>

      <div className="px-4 py-2 border-t border-terminal-border text-[10px] text-terminal-dim">
        Sliding window · 100 pts
      </div>
    </aside>
  );
}
