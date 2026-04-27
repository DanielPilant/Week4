# Real-Time Market Data Stream Processing

OLTP-style online stream processing of Finnhub trade ticks for 10 Technology / ETF
tickers, with an offline batch-validation pass to prove correctness, latency, and
memory efficiency.

---

## Team Members

| Member          | Student ID  |
| --------------- | ----------- |
| Daniel Pilant   | 214631426   |
| Elyasaf Okanin  | 319028064   |

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

| File                          | Purpose                                                 |
| ----------------------------- | ------------------------------------------------------- |
| `console.finnhub.txt`         | Raw JSON ticks + system timestamp (one per line)        |
| `console.process_stream.txt`  | Processed CSV row every 100 messages per ticker         |
| `console.latency.txt`         | Online latency + peak-memory metrics                    |
| `console.comparison.txt`      | Output of `offline_validation.py`                       |
| `stream_errors.log`           | Errors raised by malformed messages or the WS client    |

---

## Prerequisites

| Tool      | Tested version | Purpose                                  |
| --------- | -------------- | ---------------------------------------- |
| Git       | any modern     | Clone the repo                           |
| Python    | 3.10+          | Backend stream processor + bridge        |
| Node.js   | 18.17+ / 20+   | Frontend dashboard (Next.js 14)          |
| npm       | 9+             | Frontend package manager                 |
| Finnhub   | Free tier OK   | API key from https://finnhub.io          |

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

* `console.finnhub.txt` — raw JSON ticks
* `console.process_stream.txt` — processed CSV rows (one block per 100 msgs/ticker)
* `console.latency.txt` — latency + peak-memory metrics (on shutdown)
* `stream_errors.log` — any errors

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

* **`websocket-client` not found** — make sure the venv is active (`which python`
  should point inside `backend/.venv/`).
* **Frontend shows no data** — confirm `bridge_server` is running and that
  `console.process_stream.txt` is being appended to. The bridge polls the file
  every 150 ms.
* **`401 Unauthorized` on the WS** — your Finnhub API key is missing or invalid.
* **Port already in use** — change `8765` (bridge) or `3000` (frontend) and
  update the matching value in [frontend/lib/](frontend/lib/).

---

## Architecture (Online Phase)

* **WebSocket** to `wss://ws.finnhub.io?token=<KEY>`, subscribes 10 tickers.
* **First action** in `on_message` is to write the raw JSON + system timestamp
  to `console.finnhub.txt` — one record per line.
* **Per-ticker state** is a fixed-size dictionary entry. No growing lists.
* **Continuous-time EMA** with `H = 10 min` and `H = 50 min`:

  ```
  alpha = 1 - exp(ln(0.5) * (delta_t / H))
  EMA   = alpha * price + (1 - alpha) * EMA_prev
  ```

  `delta_t` is computed from the `t` field of consecutive Finnhub trades, so
  EMA respects the actual data clock.
* **Welford's algorithm** for running variance: maintain `count`, `mean`, `M2`;
  variance = `M2 / count`. Two parallel accumulators are kept so the rubric's
  `var10`/`var50` columns are populated.
* **Min / Max** updated in O(1) on every tick.
* **Processed rows** are emitted every 100 messages **per ticker**:

  ```
  time, data time, ticker, EMA10, var10, ss10, count10,
                          EMA50, var50, ss50, count50,
                          close, min, max
  ```
* **Latency** is measured around the entire `on_message` body via
  `time.perf_counter()`. Running mean / max only — no growing list.
* **Peak memory** is tracked with `tracemalloc` and dumped at shutdown.
* **Errors** are surfaced through the `logging` module, never silenced.

---

## Sample Results Table

| time (ISO UTC)              | data time (ISO UTC)         | ticker | EMA10  | var10 | ss10  | count10 | EMA50  | var50 | ss50  | count50 | close  | min    | max    |
| --------------------------- | --------------------------- | ------ | ------ | ----- | ----- | ------- | ------ | ----- | ----- | ------- | ------ | ------ | ------ |
| 2026-04-27T13:00:01.234Z    | 2026-04-27T13:00:00.987Z    | AAPL   | 187.34 | 0.041 | 4.10  | 100     | 187.40 | 0.041 | 4.10  | 100     | 187.32 | 187.10 | 187.55 |
| `<TIME>`                    | `<DATA_TIME>`               | `<T>`  | `<F>`  | `<F>` | `<F>` | `<INT>` | `<F>`  | `<F>` | `<F>` | `<INT>` | `<F>`  | `<F>`  | `<F>`  |

---

## Offline Validation Comparison

### Accuracy

| Ticker | EMA10 (batch) | EMA10 (online) | \|ΔEMA10\| | EMA50 (batch) | EMA50 (online) | \|ΔEMA50\| | Var (batch) | Var10 (online) | \|ΔVar\| |
| ------ | ------------- | -------------- | ---------- | ------------- | -------------- | ---------- | ----------- | -------------- | -------- |
| AAPL   | `<F>`         | `<F>`          | `<F>`      | `<F>`         | `<F>`          | `<F>`      | `<F>`       | `<F>`          | `<F>`    |
| MSFT   | `<F>`         | `<F>`          | `<F>`      | `<F>`         | `<F>`          | `<F>`      | `<F>`       | `<F>`          | `<F>`    |
| ...    | ...           | ...            | ...        | ...           | ...            | ...        | ...         | ...            | ...      |

### Performance

| Metric                      | Online            | Offline (batch) |
| --------------------------- | ----------------- | --------------- |
| Avg latency per update      | `<X>` µs          | —               |
| Max latency per update      | `<X>` µs          | —               |
| Total runtime               | 1 h (wall clock)  | `<X>` s         |
| Trades processed            | `<N>`             | `<N>`           |

### Memory

| Metric              | Online             | Offline           |
| ------------------- | ------------------ | ----------------- |
| Peak memory         | `<BYTES>`          | `<BYTES>`         |
| Ratio (off / on)    | —                  | `<X>`x            |

---

## Verbal Analysis

> **Accuracy.** _<Discuss |ΔEMA| and |ΔVar| values. The online EMA matches the
> batch EMA up to floating-point error because both apply the identical
> continuous-time decay rule on the same data clock. The Welford running
> variance equals the batch population variance (`Σ(xᵢ - x̄)² / n`) by the
> Welford invariant `M₂ = Σ(xᵢ - x̄)²`.>_

> **Performance.** _<Compare the average per-tick latency of the online path
> (microseconds) to the total offline runtime (seconds). The online path
> performs O(1) work per tick — a few floating-point ops plus one CSV write
> every 100 ticks — whereas the offline path scans the entire raw log and
> sorts each ticker's series.>_

> **Memory.** _<The online processor keeps a fixed scalar state per ticker, so
> peak memory is bounded by `O(|tickers|)` regardless of stream length. The
> offline validator must materialise the full trade list, so its peak memory
> grows with `O(N)` ticks.>_

> **Bottlenecks.** _<Discuss WS client thread, file flushing cadence, JSON
> parsing cost, network jitter on Finnhub's free tier, etc.>_

> **Dropped messages.** _<Report `total_messages_received` vs.
> `total_trades_processed` from `console.latency.txt`, plus any malformed
> entries logged in `stream_errors.log`. Discuss whether the system kept up
> with peak market arrival rate.>_

---

## Strict Constraints Honoured

* O(1) memory per ticker — only scalar fields in the state dict.
* No statistic recomputed from scratch on each tick — all updates are
  incremental.
* `delta_t` for EMA derived from the Finnhub `t` field of consecutive trades.
* `logging` used for all errors; no silent drops.
* f-strings used throughout for clean formatting.
