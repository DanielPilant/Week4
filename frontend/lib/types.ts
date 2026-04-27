// Shape of one parsed block as broadcast by bridge_server.py
export type Tick = {
  symbol:    string;
  data_time: string | null;
  now:       string | null;
  ts:        number;     // epoch ms — chart x-axis
  close:     number;
  ema10:     number;
  ema50:     number;
  min10:     number;
  max10:     number;
  min50:     number;
  max50:     number;
  var10:     number;
  var50:     number;
  count10:   number;
  count50:   number;
};

export const TICKERS = [
  "AAPL", "MSFT", "GOOGL", "AMZN", "META",
  "NVDA", "TSLA", "QQQ",  "SPY",   "VOO",
] as const;

export type Ticker = (typeof TICKERS)[number];

export const HISTORY_LIMIT = 100;
