"""
offline_validation.py
Batch (offline) validation of the online stream processor.

Reads the raw tick log produced by finnhub_stream.py (console.finnhub.txt)
and recomputes EMA10 / EMA50 / variance / min / max per ticker using a
straight batch pass. The batch results are then compared against the
final online snapshot in console.process_stream.txt.

Outputs console.comparison.txt summarising:
  * accuracy   : |EMA_batch - EMA_online|, |Var_batch - Var_online|
  * performance: average online per-tick latency vs. total offline runtime
  * memory     : online peak memory vs. offline peak memory (tracemalloc)
"""

import json
import math
import time
import tracemalloc
from collections import defaultdict


RAW_FILE        = "console.finnhub.txt"
PROC_FILE       = "console.process_stream.txt"
LATENCY_FILE    = "console.latency.txt"
COMPARISON_FILE = "console.comparison.txt"

H10     = 10 * 60
H50     = 50 * 60
LN_HALF = math.log(0.5)


# ======================================================================
# IO HELPERS
# ======================================================================
def parse_raw_file(path):
    """Yield trade dicts {ticker, price, ts_ms} from the raw log."""
    trades = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            parts = line.split("\t", 1)
            if len(parts) != 2:
                continue
            _, raw_json = parts
            try:
                msg = json.loads(raw_json)
            except json.JSONDecodeError:
                continue
            if msg.get("type") != "trade":
                continue
            for tr in msg.get("data") or []:
                try:
                    trades.append({
                        "ticker": tr["s"],
                        "price":  float(tr["p"]),
                        "ts_ms":  int(tr["t"]),
                    })
                except (KeyError, ValueError, TypeError):
                    continue
    return trades


def load_online_snapshots(path):
    """Return last-row-per-ticker from console.process_stream.txt block format."""
    last = {}
    current_ticker = None
    current_data = {}
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("=="):
                    if current_ticker and current_data:
                        last[current_ticker] = current_data.copy()
                    continue

                if "=" in line:
                    parts = line.split("=")
                    if len(parts) == 2:
                        key = parts[0].strip()
                        val = parts[1].strip().rstrip(";") 
                        
                        if key == "symbol":
                            current_ticker = val
                        elif key in ["EMA10", "var10", "ss10", "count10", "EMA50", "var50", "ss50", "count50"]:
                            current_data[key.lower()] = float(val)
    except FileNotFoundError:
        pass
        
    return last

def load_online_metrics(path):
    info = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    info[k] = v
    except FileNotFoundError:
        pass
    return info


# ======================================================================
# BATCH COMPUTATION (EXACT REFERENCE)
# ======================================================================
def batch_compute(trades):
    """Recompute ground-truth stats per ticker from the raw stream."""
    by_ticker = defaultdict(list)
    for t in trades:
        by_ticker[t["ticker"]].append((t["ts_ms"], t["price"]))

    results = {}
    for ticker, series in by_ticker.items():
        series.sort(key=lambda x: x[0])
        prices = [p for _, p in series]
        n      = len(prices)

        # Continuous-time EMA, walked across the full series
        ema10 = ema50 = None
        last_ts = None
        for ts_ms, p in series:
            ts = ts_ms / 1000.0
            if last_ts is None:
                ema10 = p
                ema50 = p
            else:
                dt = max(0.0, ts - last_ts)
                a10 = 1.0 - math.exp(LN_HALF * (dt / H10))
                a50 = 1.0 - math.exp(LN_HALF * (dt / H50))
                ema10 = a10 * p + (1.0 - a10) * ema10
                ema50 = a50 * p + (1.0 - a50) * ema50
            last_ts = ts

        if n > 0:
            mean = sum(prices) / n
            var  = sum((x - mean) ** 2 for x in prices) / n   # population variance == M2/count
            mn, mx = min(prices), max(prices)
        else:
            mean = var = mn = mx = 0.0

        results[ticker] = {
            "count": n,
            "ema10": ema10 if ema10 is not None else 0.0,
            "ema50": ema50 if ema50 is not None else 0.0,
            "mean":  mean,
            "var":   var,
            "min":   mn,
            "max":   mx,
        }
    return results


# ======================================================================
# REPORT
# ======================================================================
def build_report(batch, online, online_metrics, offline_runtime, offline_peak):
    out = []
    out.append("=" * 78)
    out.append("OFFLINE VALIDATION SUMMARY")
    out.append("=" * 78)

    out.append("")
    out.append("--- PERFORMANCE ---")
    avg_lat = float(online_metrics.get("avg_latency_seconds", "0") or 0.0)
    max_lat = float(online_metrics.get("max_latency_seconds", "0") or 0.0)
    n_lat   = int(online_metrics.get("latency_count", "0") or 0)
    out.append(f"Online average latency : {avg_lat * 1e6:12.3f} microseconds  (n={n_lat})")
    out.append(f"Online max latency     : {max_lat * 1e6:12.3f} microseconds")
    out.append(f"Offline batch runtime  : {offline_runtime:12.4f} seconds")

    out.append("")
    out.append("--- MEMORY ---")
    online_peak = int(online_metrics.get("online_peak_memory_bytes", "0") or 0)
    out.append(f"Online peak memory     : {online_peak:>14d} bytes")
    out.append(f"Offline peak memory    : {offline_peak:>14d} bytes")
    if online_peak > 0:
        ratio = offline_peak / online_peak
        out.append(f"Offline / Online ratio : {ratio:>14.2f}x")

    out.append("")
    out.append("--- ACCURACY (last online snapshot vs. full-history batch) ---")
    header = (
        "ticker  count_b  count_o  "
        "ema10_b      ema10_o      |dEMA10|     "
        "ema50_b      ema50_o      |dEMA50|     "
        "var_b        var10_o      |dVar10|     var50_o      |dVar50|"
    )
    out.append(header)
    out.append("-" * len(header))

    sum_d_ema10 = sum_d_ema50 = sum_d_var10 = sum_d_var50 = 0.0
    compared = 0
    for ticker in sorted(batch.keys()):
        b = batch[ticker]
        o = online.get(ticker)
        if o is None:
            out.append(f"{ticker:<6}  {b['count']:>7d}  {'NA':>7}  "
                       f"{b['ema10']:11.4f}  {'NA':>11}  {'NA':>11}  "
                       f"{b['ema50']:11.4f}  {'NA':>11}  {'NA':>11}  "
                       f"{b['var']:11.4f}  {'NA':>11}  {'NA':>11}  {'NA':>11}  {'NA':>11}")
            continue
        d_ema10 = abs(b["ema10"] - o["ema10"])
        d_ema50 = abs(b["ema50"] - o["ema50"])
        d_var10 = abs(b["var"]   - o["var10"])
        d_var50 = abs(b["var"]   - o["var50"])
        sum_d_ema10 += d_ema10
        sum_d_ema50 += d_ema50
        sum_d_var10 += d_var10
        sum_d_var50 += d_var50
        compared += 1
        out.append(
            f"{ticker:<6}  {b['count']:>7d}  {int(o['count10']):>7d}  "
            f"{b['ema10']:11.4f}  {o['ema10']:11.4f}  {d_ema10:11.4f}  "
            f"{b['ema50']:11.4f}  {o['ema50']:11.4f}  {d_ema50:11.4f}  "
            f"{b['var']:11.4f}  {o['var10']:11.4f}  {d_var10:11.4f}  "
            f"{o['var50']:11.4f}  {d_var50:11.4f}"
        )

    if compared:
        out.append("")
        out.append("--- AGGREGATE ABSOLUTE DIFFERENCES ---")
        out.append(f"mean |dEMA10| : {sum_d_ema10 / compared:.6f}")
        out.append(f"mean |dEMA50| : {sum_d_ema50 / compared:.6f}")
        out.append(f"mean |dVar10|: {sum_d_var10 / compared:.6f}")
        out.append(f"mean |dVar50|: {sum_d_var50 / compared:.6f}")

    return "\n".join(out)


# ======================================================================
# MAIN
# ======================================================================
def main():
    tracemalloc.start()
    t0 = time.perf_counter()

    trades = parse_raw_file(RAW_FILE)
    batch  = batch_compute(trades)

    offline_runtime = time.perf_counter() - t0
    _, offline_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    online         = load_online_snapshots(PROC_FILE)
    online_metrics = load_online_metrics(LATENCY_FILE)

    report = build_report(batch, online, online_metrics, offline_runtime, offline_peak)

    with open(COMPARISON_FILE, "w", encoding="utf-8") as f:
        f.write(report + "\n")

    print(report)
    print(f"\nWritten: {COMPARISON_FILE}")


if __name__ == "__main__":
    main()
