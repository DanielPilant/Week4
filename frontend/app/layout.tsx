import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Finnhub Stream Terminal",
  description: "Real-time EMA crossover dashboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="font-mono bg-terminal-bg text-terminal-text antialiased">
        {children}
      </body>
    </html>
  );
}
