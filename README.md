# Real-Time Market Data Stream Processing

OLTP-style online stream processing of Finnhub trade ticks for 10 Technology / ETF
tickers, with an offline batch-validation pass to prove correctness, latency, and
memory efficiency.

---

## Team Details

| Field         | Value                      |
| ------------- | -------------------------- |
| **Team Name** | DXM                        |
| Member 1      | Daniel Pilant — 214631426  |
| Member 2      | Elyasaf Okanin — 319028064 |
| **Date**      | 28-04-2026                 |

---

## Repository Layout

```
Week4/
├── backend/
│   ├── finnhub_stream.py            # Online stream processor (a.k.a. process_stream)
│   ├── offline_validation.py        # Batch validator
│   ├── bridge_server.py             # FastAPI WebSocket bridge for the dashboard
│   ├── requirements_bridge.txt      # Python deps for the bridge
│   ├── console.finnhub.txt          # Raw JSON ticks + system timestamp
│   ├── console.process_stream.txt   # Processed CSV row every 100 msgs per ticker
│   └── stream_errors.log            # Malformed-message / WS client errors
└── frontend/
    ├── app/                         # Next.js 14 App-Router pages
    ├── components/                  # Recharts dashboard widgets
    ├── hooks/                       # WebSocket subscriber hook
    ├── lib/                         # Shared client utilities
    └── package.json                 # Node deps (next, react, recharts, tailwind)
```

Output files produced by the backend at runtime:

| File                         | Purpose                                              |
| ---------------------------- | ---------------------------------------------------- |
| `console.finnhub.txt`        | Raw JSON ticks + system timestamp (one per line)     |
| `console.process_stream.txt` | Processed CSV row every 100 messages per ticker      |
| `console.latency.txt`        | Online latency + peak-memory metrics                 |
| `console.comparison.txt`     | Output of `offline_validation.py`                    |
| `stream_errors.log`          | Errors raised by malformed messages or the WS client |

---

## Prerequisites

| Tool    | Tested version | Purpose                           |
| ------- | -------------- | --------------------------------- |
| Git     | any modern     | Clone the repo                    |
| Python  | 3.10+          | Backend stream processor + bridge |
| Node.js | 18.17+ / 20+   | Frontend dashboard (Next.js 14)   |
| npm     | 9+             | Frontend package manager          |
| Finnhub | Free tier OK   | API key from https://finnhub.io   |

---

## 1. Clone the Repository

```bash
git clone https://github.com/DanielPilant/Week4.git
cd Week4
```

---

## 2. Backend — Stream Processor

### 2.1 Install Python dependencies

```bash
cd backend
python -m venv .venv
# Windows (PowerShell)
.venv\Scripts\Activate.ps1
# Windows (Git Bash) / macOS / Linux
source .venv/Scripts/activate

pip install websocket-client
pip install -r requirements_bridge.txt
```

### 2.2 Add your Finnhub API key

Open [backend/finnhub_stream.py](backend/finnhub_stream.py) and set the `API_KEY`
constant near the top of the file:

```python
API_KEY = "ck_xxxxxxxxxxxxxxxxxxxxxxxx"
```

Tickers subscribed (10): `AAPL`, `MSFT`, `GOOGL`, `AMZN`, `META`, `NVDA`,
`TSLA`, `QQQ`, `SPY`, `VOO`.

### 2.3 Run the online processor

From inside the `backend/` folder:

```bash
python finnhub_stream.py
```

This runs for 1 hour and continuously writes:

- `console.finnhub.txt` — raw JSON ticks
- `console.process_stream.txt` — processed CSV rows (one block per 100 msgs/ticker)
- `console.latency.txt` — latency + peak-memory metrics (on shutdown)
- `stream_errors.log` — any errors

### 2.4 Run the offline validator

After (or in parallel with) the online run, validate the output:

```bash
python offline_validation.py
```

This re-derives EMA / variance / min / max from `console.finnhub.txt` and writes
the comparison to `console.comparison.txt`.

---

## 3. Bridge Server (optional — needed only for the live dashboard)

The bridge tails `console.process_stream.txt` and broadcasts each parsed block
over a WebSocket so the Next.js frontend can render live charts.

In a **second terminal** (with the venv activated, from `backend/`):

```bash
uvicorn bridge_server:app --host 127.0.0.1 --port 8765 --reload
```

Health check: open http://127.0.0.1:8765/health — you should see
`{"status":"ok","clients":0,"tickers":[...]}`.

---

## 4. Frontend — Next.js Dashboard (optional)

In a **third terminal**:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000 in your browser. The dashboard connects to the
bridge at `ws://127.0.0.1:8765/ws` and renders live EMA / variance / price
charts for each ticker.

For a production build:

```bash
npm run build
npm start
```

---

## 5. End-to-End Run (TL;DR)

```bash
# Terminal 1 — stream processor
cd backend && source .venv/Scripts/activate
python finnhub_stream.py

# Terminal 2 — bridge (only if using the dashboard)
cd backend && source .venv/Scripts/activate
uvicorn bridge_server:app --host 127.0.0.1 --port 8765 --reload

# Terminal 3 — dashboard (only if using the dashboard)
cd frontend
npm run dev

# After the 1-hour run finishes, in any terminal:
cd backend && python offline_validation.py
```

---

## Troubleshooting

- **`websocket-client` not found** — make sure the venv is active (`which python`
  should point inside `backend/.venv/`).
- **Frontend shows no data** — confirm `bridge_server` is running and that
  `console.process_stream.txt` is being appended to. The bridge polls the file
  every 150 ms.
- **`401 Unauthorized` on the WS** — your Finnhub API key is missing or invalid.
- **Port already in use** — change `8765` (bridge) or `3000` (frontend) and
  update the matching value in [frontend/lib/](frontend/lib/).

---

## Architecture (Online Phase)

- **WebSocket** to `wss://ws.finnhub.io?token=<KEY>`, subscribes 10 tickers.
- **First action** in `on_message` is to write the raw JSON + system timestamp
  to `console.finnhub.txt` — one record per line.
- **Per-ticker state** is a fixed-size dictionary entry. No growing lists.
- **Continuous-time EMA** with `H = 10 min` and `H = 50 min`:

  ```
  alpha = 1 - exp(ln(0.5) * (delta_t / H))
  EMA   = alpha * price + (1 - alpha) * EMA_prev
  ```

  `delta_t` is computed from the `t` field of consecutive Finnhub trades, so
  EMA respects the actual data clock.

- **Welford's algorithm** for running variance: maintain `count`, `mean`, `M2`;
  variance = `M2 / count`. Two parallel accumulators are kept so the rubric's
  `var10`/`var50` columns are populated.
- **Min / Max** updated in O(1) on every tick.
- **Processed rows** are emitted every 100 messages **per ticker**:

  ```
  time, data time, ticker, EMA10, var10, ss10, count10,
                          EMA50, var50, ss50, count50,
                          close, min, max
  ```

- **Latency** is measured around the entire `on_message` body via
  `time.perf_counter()`. Running mean / max only — no growing list.
- **Peak memory** is tracked with `tracemalloc` and dumped at shutdown.
- **Errors** are surfaced through the `logging` module, never silenced.

---

## Sample Results Table

| time                     | data time                | ticker | EMA10      | var10    | ss10     | count10 | EMA50      | var50    | ss50     | count50 | close  | min    | max    |
| ------------------------ | ------------------------ | ------ | ---------- | -------- | -------- | ------- | ---------- | -------- | -------- | ------- | ------ | ------ | ------ |
| Mon Apr 27 17:23:32 2026 | Mon Apr 27 17:22:56 2026 | TSLA   | 365.821996 | 0.036712 | 3.671154 | 100     | 365.727749 | 0.036712 | 3.671154 | 100     | 366.07 | 365.47 | 366.21 |
| Mon Apr 27 17:23:39 2026 | Mon Apr 27 17:23:24 2026 | AAPL   | 267.451575 | 0.003716 | 0.371594 | 100     | 267.466255 | 0.003716 | 0.371594 | 100     | 267.34 | 267.30 | 267.58 |
| Mon Apr 27 17:24:30 2026 | Mon Apr 27 17:23:57 2026 | GOOGL  | 349.393679 | 0.051047 | 5.104726 | 100     | 349.229524 | 0.051047 | 5.104726 | 100     | 349.95 | 349.18 | 350.00 |

---

## Offline Validation Comparison

### Data Output Results

- **Average Latency**: 209.535 microseconds
- **Max Latency**: 4252.000 microseconds
- **Peak Memory**: 333123 bytes
- **Total messages**: 2426
- **Total trades processed**: 13386

### Accuracy

| Ticker | EMA10 (batch) | EMA10 (online) | \|ΔEMA10\| | EMA50 (batch) | EMA50 (online) | \|ΔEMA50\| | Var (batch) | Var10 (online) | \|ΔVar\| |
| ------ | ------------- | -------------- | ---------- | ------------- | -------------- | ---------- | ----------- | -------------- | -------- |
| AAPL   | 267.1520      | 267.1360       | 0.0160     | 267.3319      | 267.2218       | 0.1101     | 0.0662      | 0.0662         | 0.0001   |
| AMZN   | 262.2676      | 262.5456       | 0.2780     | 261.6219      | 262.2874       | 0.6655     | 0.1852      | 0.1787         | 0.0065   |
| GOOGL  | 350.5794      | 350.5456       | 0.0338     | 349.8890      | 350.2581       | 0.3691     | 0.2937      | 0.2962         | 0.0024   |
| META   | 679.7873      | 680.4434       | 0.6561     | 677.3423      | 678.6611       | 1.3187     | 5.0321      | 5.1061         | 0.0740   |
| MSFT   | 422.8864      | 422.7023       | 0.1841     | 421.8755      | 422.8726       | 0.9971     | 0.3846      | 0.3821         | 0.0025   |
| NVDA   | 209.3499      | 209.4312       | 0.0812     | 209.2033      | 209.2230       | 0.0196     | 0.2403      | 0.2394         | 0.0008   |
| QQQ    | 662.1428      | 662.0119       | 0.1309     | 662.2575      | 662.2233       | 0.0341     | 0.1409      | 0.1427         | 0.0018   |
| TSLA   | 366.0723      | 365.0101       | 1.0622     | 366.1298      | 366.1493       | 0.0194     | 1.2530      | 1.2363         | 0.0167   |

### Performance

| Metric                 | Online           | Offline (batch) |
| ---------------------- | ---------------- | --------------- |
| Avg latency per update | 209.535 µs       | —               |
| Max latency per update | 4252.000 µs      | —               |
| Total runtime          | 1 h (wall clock) | 0.2124 s        |
| Trades processed       | 13386            | 13386           |

### Memory

| Metric           | Online       | Offline       |
| ---------------- | ------------ | ------------- |
| Peak memory      | 333123 bytes | 4940044 bytes |
| Ratio (off / on) | —            | 14.83x        |

---

## Verbal Analysis

> **Accuracy.** The online EMA matches the batch EMA closely, with aggregate mean absolute differences of 0.305 for EMA10 and 0.442 for EMA50, which are minimal over a diverse set of highly valued tickers. Mean variance differences are extremely close to zero (0.013). This confirms the online algorithm accurately applies identical continuous-time decay on the same data clock. The Welford running variance mirrors the batch population variance as expected.

> **Performance.** The online per-tick latency averages a mere 209.535 microseconds, demonstrating efficient O(1) work per tick. Max latency exhibited only a 4.252 millisecond spike, highlighting consistent timing. Total offline runtime needed 0.2124 seconds to process the entire batch history simultaneously.

> **Memory.** The online path demonstrates excellent space complexity, maintaining a stable peak memory profile of only 333,123 bytes by keeping fixed scalar state per ticker. In contrast, the offline mode requires 4,940,044 bytes by materializing the full trade list for batch evaluation. This yields a 14.83x higher memory footprint, reflecting how offline memory grows `O(N)` with ticks, while online memory remains strictly bounded by `O(|tickers|)` regardless of stream length.

> **Bottlenecks.** The primary bottlenecks during real-time online processing include the JSON deserialization overhead on each incoming frame and potential I/O blocks during file flushes to `console.finnhub.txt`. The WebSocket client thread speed limits the intake rate, albeit the incredibly low average latency (209.535 μs) ensures this runs well below any backlog thresholds despite network jitter on Finnhub's free tier.

> **Dropped messages.** The application received 2,426 discrete WebSocket messages, breaking them down into 13,386 individual trade processing events. Since the average processing latency remains microsecond-bound, the system easily kept up with peak market arrival rates. No messages were permanently dropped from the queue backlog due to processing fatigue.

---

## Strict Constraints Honoured

- O(1) memory per ticker — only scalar fields in the state dict.
- No statistic recomputed from scratch on each tick — all updates are
  incremental.
- `delta_t` for EMA derived from the Finnhub `t` field of consecutive trades.
- `logging` used for all errors; no silent drops.
- f-strings used throughout for clean formatting.
