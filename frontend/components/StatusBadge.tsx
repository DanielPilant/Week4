"use client";

type Props = { state: "connecting" | "open" | "closed" };

const map = {
  connecting: { label: "CONNECTING", dot: "bg-terminal-amber animate-pulse" },
  open:       { label: "LIVE",       dot: "bg-terminal-green" },
  closed:     { label: "OFFLINE",    dot: "bg-terminal-red" },
} as const;

export default function StatusBadge({ state }: Props) {
  const { label, dot } = map[state];
  return (
    <div className="inline-flex items-center gap-2 px-2 py-1 border border-terminal-border rounded text-[10px] tracking-widest">
      <span className={`w-2 h-2 rounded-full ${dot}`} />
      <span className="text-terminal-dim">{label}</span>
    </div>
  );
}
