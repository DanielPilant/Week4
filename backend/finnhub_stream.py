"""
finnhub_stream.py
Online stream processor for Finnhub trade ticks.

Maintains O(1) state per ticker using:
  * Continuous-time EMA (half-lives H=10 min and H=50 min)
  * Welford's online algorithm for running variance (count, mean, M2)
  * Running min/max
  * Running latency statistics (no growing list)

Run for 1 hour, then write a latency / memory summary for offline validation.

Outputs:
  - console.finnhub.txt        : raw JSON tick + system timestamp (one per line)
  - console.process_stream.txt : formatted row every 100 messages PER TICKER
  - console.latency.txt        : online latency + peak-memory metrics
  - stream_errors.log          : malformed-message and connection errors
"""

import json
import math
import time
import logging
import threading
import tracemalloc
from datetime import datetime, timezone

import websocket  # pip install websocket-client


# ======================================================================
# CONFIGURATION  --  PASTE YOUR FINNHUB API KEY HERE
# ======================================================================
API_KEY = "d7nfp2hr01qppri4n0ngd7nfp2hr01qppri4n0o0"

# 10 Technology / ETF tickers
TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META",
    "NVDA", "TSLA", "QQQ",  "SPY",   "VOO",
]

RUN_DURATION_SECONDS = 60 * 60   # 1 continuous hour
LOG_EVERY_N          = 100       # processed-row cadence per ticker

RAW_FILE     = "console.finnhub.txt"
PROC_FILE    = "console.process_stream.txt"
LATENCY_FILE = "console.latency.txt"
ERROR_LOG    = "stream_errors.log"

# Continuous-time EMA half-lives (in seconds, matching trade timestamp units)
H10      = 10 * 60
H50      = 50 * 60
LN_HALF  = math.log(0.5)


# ======================================================================
# LOGGING
# ======================================================================
file_handler = logging.FileHandler(ERROR_LOG, mode="w")
file_handler.setLevel(logging.ERROR)

stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.INFO)

logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[file_handler, stream_handler],
)
log = logging.getLogger("finnhub_stream")

# ======================================================================
# STATE  --  O(1) per ticker, no growing lists
# ======================================================================
state = {}                # ticker -> dict of running scalars

# Running latency stats (also O(1))
latency_count = 0
latency_sum   = 0.0
latency_max   = 0.0
total_messages_received = 0
total_trades_processed  = 0

# Single, persistent file handles -- reopening per tick would dominate latency.
raw_fh  = None
proc_fh = None


def init_ticker_state(ticker):
    state[ticker] = {
        "last_ts":   None,   # last data-time in seconds
        "ema10":     None,
        "ema50":     None,
        # Welford accumulators (parallel trackers preserve the var10/var50 columns)
        "count10":   0, "mean10": 0.0, "m2_10": 0.0,
        "count50":   0, "mean50": 0.0, "m2_50": 0.0,
        "min_p":     None,
        "max_p":     None,
        "msg_count": 0,
        "last_price": None,
    }


# ======================================================================
# ONLINE ALGORITHMS
# ======================================================================
def update_welford(count, mean, m2, x):
    """Welford's online update. Returns updated (count, mean, m2)."""
    count += 1
    delta  = x - mean
    mean  += delta / count
    delta2 = x - mean
    m2    += delta * delta2
    return count, mean, m2


def compute_alpha(delta_t, H):
    """Continuous-time EMA decay: alpha = 1 - exp(ln(0.5) * (delta_t / H))."""
    return 1.0 - math.exp(LN_HALF * (delta_t / H))


def update_ema(prev_ema, price, delta_t, H):
    if prev_ema is None or delta_t <= 0.0:
        return price if prev_ema is None else prev_ema
    alpha = compute_alpha(delta_t, H)
    return alpha * price + (1.0 - alpha) * prev_ema


def process_trade(ticker, price, ts_ms):
    """Pure-scalar update of one ticker's state. O(1) work, O(1) memory."""
    if ticker not in state:
        init_ticker_state(ticker)
    s = state[ticker]

    ts = ts_ms / 1000.0  # Finnhub timestamps are in ms
    delta_t = 0.0 if s["last_ts"] is None else max(0.0, ts - s["last_ts"])

    s["ema10"] = update_ema(s["ema10"], price, delta_t, H10)
    s["ema50"] = update_ema(s["ema50"], price, delta_t, H50)

    s["count10"], s["mean10"], s["m2_10"] = update_welford(
        s["count10"], s["mean10"], s["m2_10"], price)
    s["count50"], s["mean50"], s["m2_50"] = update_welford(
        s["count50"], s["mean50"], s["m2_50"], price)

    if s["min_p"] is None or price < s["min_p"]:
        s["min_p"] = price
    if s["max_p"] is None or price > s["max_p"]:
        s["max_p"] = price

    s["last_price"] = price
    s["last_ts"]    = ts
    s["msg_count"] += 1
    return s


# ======================================================================
# OUTPUT WRITERS
# ======================================================================
def write_processed_row(ticker, data_ts_ms, s):
    var10 = (s["m2_10"] / s["count10"]) if s["count10"] else 0.0
    var50 = (s["m2_50"] / s["count50"]) if s["count50"] else 0.0
    
    sys_ts_str = datetime.now().strftime("%a %b %d %H:%M:%S %Y")
    data_ts_str = datetime.fromtimestamp(data_ts_ms / 1000.0).strftime("%a %b %d %H:%M:%S %Y")

    block = (
        "===================================\n"
        f"symbol     = {ticker};\n"
        f"data_time  = {data_ts_str}\n"
        f"now        = {sys_ts_str}\n"
        f"close      = {s['last_price']:.6f}\n"
        f"EMA10      = {s['ema10']:.6f}\n"
        f"min10      = {s['min_p']:.6f}\n" 
        f"max10      = {s['max_p']:.6f}\n"
        f"count10    = {s['count10']}\n"
        f"ss10       = {s['m2_10']:.6f}\n"
        f"var10      = {var10:.6f}\n"
        f"EMA50      = {s['ema50']:.6f}\n"
        f"min50      = {s['min_p']:.6f}\n"
        f"max50      = {s['max_p']:.6f}\n"
        f"count50    = {s['count50']}\n"
        f"ss50       = {s['m2_50']:.6f}\n"
        f"var50      = {var50:.6f}\n"
        "===================================\n"
    )
    proc_fh.write(block)

# ======================================================================
# WEBSOCKET CALLBACKS
# ======================================================================
def on_message(ws, message):
    """First action: persist raw message + system timestamp. Then update O(1) state."""
    global latency_count, latency_sum, latency_max
    global total_messages_received, total_trades_processed

    t_start = time.perf_counter()
    sys_ts  = datetime.now(timezone.utc).isoformat()

    # 1) Raw log -- absolute first action
    try:
        raw_fh.write(f"{sys_ts}\t{message}\n")
    except Exception as exc:
        log.error(f"raw write failed: {exc}")
        return

    total_messages_received += 1

    # 2) Parse
    try:
        msg = json.loads(message)
    except json.JSONDecodeError as exc:
        log.error(f"malformed JSON: {exc}; raw={message!r}")
        return

    msg_type = msg.get("type")
    if msg_type == "ping":
        return
    if msg_type != "trade":
        return  # subscription confirmations etc.

    data = msg.get("data")
    if not data:
        log.error(f"trade message missing 'data': {msg}")
        return

    # 3) Update state and write processed rows
    for trade in data:
        try:
            ticker = trade["s"]
            price  = float(trade["p"])
            ts_ms  = int(trade["t"])
        except (KeyError, ValueError, TypeError) as exc:
            log.error(f"malformed trade entry: {exc}; trade={trade!r}")
            continue

        s = process_trade(ticker, price, ts_ms)
        total_trades_processed += 1

        if s["msg_count"] % LOG_EVERY_N == 0:
            try:
                write_processed_row(ticker, ts_ms, s)
            except Exception as exc:
                log.error(f"processed write failed: {exc}")

    # 4) Latency (running stats only, O(1))
    elapsed = time.perf_counter() - t_start
    latency_count += 1
    latency_sum   += elapsed
    if elapsed > latency_max:
        latency_max = elapsed


def on_error(ws, error):
    log.error(f"websocket error: {error}")


def on_close(ws, code, msg):
    log.info(f"websocket closed code={code} msg={msg}")


def on_open(ws):
    log.info("websocket opened, subscribing...")
    for t in TICKERS:
        ws.send(json.dumps({"type": "subscribe", "symbol": t}))
        log.info(f"subscribed: {t}")


# ======================================================================
# DRIVER
# ======================================================================
def stop_after_duration(ws, duration):
    time.sleep(duration)
    log.info(f"run duration {duration}s elapsed, closing websocket")
    try:
        ws.close()
    except Exception as exc:
        log.error(f"close failed: {exc}")


def write_run_summary():
    """Persist online metrics (latency + peak memory) for offline_validation.py."""
    avg = (latency_sum / latency_count) if latency_count else 0.0
    current_mem, peak_mem = tracemalloc.get_traced_memory()

    summary = (
        f"total_messages_received={total_messages_received}\n"
        f"total_trades_processed={total_trades_processed}\n"
        f"latency_count={latency_count}\n"
        f"latency_sum_seconds={latency_sum:.6f}\n"
        f"avg_latency_seconds={avg:.9f}\n"
        f"max_latency_seconds={latency_max:.9f}\n"
        f"online_peak_memory_bytes={peak_mem}\n"
        f"online_current_memory_bytes={current_mem}\n"
        f"tickers_seen={len(state)}\n"
    )
    with open(LATENCY_FILE, "w", encoding="utf-8") as f:
        f.write(summary)
    log.info("run summary written:\n" + summary)


def main():
    global raw_fh, proc_fh

    if not API_KEY or API_KEY == "YOUR_FINNHUB_API_KEY_HERE":
        raise SystemExit("Paste your Finnhub API key into API_KEY at the top of this file.")

    # Truncate output files at startup; keep handles open for the whole run.
    raw_fh  = open(RAW_FILE,  "w", encoding="utf-8", buffering=1)
    proc_fh = open(PROC_FILE, "w", encoding="utf-8", buffering=1)

    tracemalloc.start()

    url = f"wss://ws.finnhub.io?token={API_KEY}"
    ws = websocket.WebSocketApp(
        url,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )

    threading.Thread(
        target=stop_after_duration, args=(ws, RUN_DURATION_SECONDS), daemon=True
    ).start()

    try:
        ws.run_forever()
    finally:
        try:
            write_run_summary()
        finally:
            tracemalloc.stop()
            for fh in (raw_fh, proc_fh):
                try:
                    fh.close()
                except Exception:
                    pass


if __name__ == "__main__":
    main()

