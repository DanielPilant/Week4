# Real-Time Market Data Stream Processing

OLTP-style online stream processing of Finnhub trade ticks for 10 Technology / ETF
tickers, with an offline batch-validation pass to prove correctness, latency, and
memory efficiency.

---

## Team Details

| Field        | Value                       |
| ------------ | --------------------------- |
| Team Name    | `<TEAM_NAME>`               |
| Member 1     | `<NAME>` — `<STUDENT_ID>`   |
| Member 2     | `<NAME>` — `<STUDENT_ID>`   |
| Member 3     | `<NAME>` — `<STUDENT_ID>`   |
| Member 4     | `<NAME>` — `<STUDENT_ID>`   |
| Submission   | `<YYYY-MM-DD>`              |

---

## Files

| File                          | Purpose                                                 |
| ----------------------------- | ------------------------------------------------------- |
| `finnhub_stream.py`           | Online stream processor (this is also `process_stream`) |
| `offline_validation.py`       | Batch validator that re-derives stats from raw log      |
| `console.finnhub.txt`         | Raw JSON ticks + system timestamp (one per line)        |
| `console.process_stream.txt`  | Processed CSV row every 100 messages per ticker         |
| `console.latency.txt`         | Online latency + peak-memory metrics                    |
| `console.comparison.txt`      | Output of `offline_validation.py`                       |
| `stream_errors.log`           | Errors raised by malformed messages or the WS client    |

---

## Setup

```bash
pip install websocket-client
```

Open `finnhub_stream.py` and paste your key into the `API_KEY` constant at the top:

```python
API_KEY = "ck_xxxxxxxxxxxxxxxxxxxxxxxx"
```

Tickers (10): AAPL, MSFT, GOOGL, AMZN, META, NVDA, TSLA, QQQ, SPY, VOO.

---

## Execution

```bash
# 1) Run the online processor for 1 hour (writes raw + processed logs)
python finnhub_stream.py
# (equivalent rename if your assignment requires it)
python process_stream.py

# 2) Validate the online output against a batch recomputation
python offline_validation.py
```

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
