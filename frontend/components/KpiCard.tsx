"use client";

type Props = {
  label:    string;
  value:    string;
  sub?:     string;
  tone?:    "neutral" | "up" | "down" | "warn";
};

const toneClass: Record<NonNullable<Props["tone"]>, string> = {
  neutral: "text-terminal-text",
  up:      "text-terminal-green",
  down:    "text-terminal-red",
  warn:    "text-terminal-amber",
};

export default function KpiCard({ label, value, sub, tone = "neutral" }: Props) {
  return (
    <div className="bg-terminal-panel border border-terminal-border rounded-md px-4 py-3 shadow-panel">
      <div className="text-[10px] uppercase tracking-widest text-terminal-dim">{label}</div>
      <div className={`mt-1 text-2xl tabular-nums leading-tight ${toneClass[tone]}`}>{value}</div>
      {sub ? <div className="mt-0.5 text-[11px] text-terminal-dim tabular-nums">{sub}</div> : null}
    </div>
  );
}
