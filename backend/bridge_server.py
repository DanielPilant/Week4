"""
bridge_server.py
WebSocket bridge between finnhub_stream.py's text output and the browser.

Tails `console.process_stream.txt`, parses each ===-delimited block into JSON,
and broadcasts the JSON to every connected WebSocket client. Also keeps a
small in-memory ring buffer per ticker so newly-connected clients receive a
short history immediately instead of staring at an empty chart.

Run:
    uvicorn bridge_server:app --host 127.0.0.1 --port 8765 --reload

Endpoints:
    GET  /health          -> {"status":"ok", "clients":N, "tickers":[...]}
    WS   /ws              -> stream of JSON messages, one per parsed block
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import Deque, Dict, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware


# --- Config ------------------------------------------------------------------
PROC_FILE = Path(os.environ.get(
    "PROC_FILE",
    Path(__file__).parent / "console.process_stream.txt",
)).resolve()

POLL_INTERVAL_SECONDS = 0.15
HISTORY_PER_TICKER    = 100
SEPARATOR_PREFIX      = "==="

FIELD_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?);?\s*$")


# --- App / state -------------------------------------------------------------
app = FastAPI(title="Finnhub Stream Bridge")

# Permissive CORS — this is a localhost dev tool, not a public service.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

clients: Set[WebSocket] = set()
history: Dict[str, Deque[dict]] = defaultdict(lambda: deque(maxlen=HISTORY_PER_TICKER))
broadcast_lock = asyncio.Lock()


# --- Block parsing -----------------------------------------------------------
def _parse_block_time(s: str) -> int | None:
    """Parse a 'Mon Apr 27 12:34:56 2026' timestamp into epoch ms."""
    if not s:
        return None
    try:
        return int(datetime.strptime(s.strip(), "%a %b %d %H:%M:%S %Y").timestamp() * 1000)
    except ValueError:
        return None


def parse_block(lines: list[str]) -> dict | None:
    """Turn a list of 'name = value' lines into a typed dict, or None if invalid."""
    fields: Dict[str, str] = {}
    for line in lines:
        m = FIELD_RE.match(line)
        if m:
            fields[m.group(1)] = m.group(2).strip().rstrip(";").strip()

    if "symbol" not in fields:
        return None

    def num(key: str, cast=float, default=0.0):
        try:
            return cast(fields[key])
        except (KeyError, ValueError):
            return default

    data_ts = _parse_block_time(fields.get("data_time", "")) or int(time.time() * 1000)

    return {
        "symbol":    fields["symbol"],
        "data_time": fields.get("data_time"),
        "now":       fields.get("now"),
        "ts":        data_ts,                        # epoch ms — chart x-axis
        "close":     num("close"),
        "ema10":     num("EMA10"),
        "ema50":     num("EMA50"),
        "min10":     num("min10"),
        "max10":     num("max10"),
        "min50":     num("min50"),
        "max50":     num("max50"),
        "var10":     num("var10"),
        "var50":     num("var50"),
        "count10":   num("count10", int, 0),
        "count50":   num("count50", int, 0),
    }


# --- Tail loop ---------------------------------------------------------------
async def _broadcast(payload: dict) -> None:
    """Send one JSON message to every connected client; drop dead sockets."""
    if not clients:
        return
    msg = json.dumps({"type": "tick", "data": payload})
    dead: list[WebSocket] = []
    async with broadcast_lock:
        for ws in clients:
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            clients.discard(ws)


async def tail_proc_file() -> None:
    """Background task: tail PROC_FILE and broadcast every complete block.

    Handles two real-world quirks:
      * file doesn't exist yet (wait for the producer to start)
      * file is truncated mid-run (producer restarted with mode='w') -> reopen
    """
    print(f"[bridge] tailing {PROC_FILE}")

    while not PROC_FILE.exists():
        await asyncio.sleep(0.5)

    fh = open(PROC_FILE, "r", encoding="utf-8", errors="replace")
    last_size = 0
    buffer: list[str] = []
    in_block = False

    try:
        while True:
            try:
                size = PROC_FILE.stat().st_size
                if size < last_size:
                    fh.close()
                    fh = open(PROC_FILE, "r", encoding="utf-8", errors="replace")
                    buffer.clear()
                    in_block = False
                last_size = size
            except OSError:
                pass

            line = fh.readline()
            if not line:
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                continue

            stripped = line.rstrip("\r\n")

            if stripped.startswith(SEPARATOR_PREFIX):
                if in_block:
                    block = parse_block(buffer)
                    if block is not None:
                        history[block["symbol"]].append(block)
                        await _broadcast(block)
                    buffer.clear()
                    in_block = False
                else:
                    in_block = True
                    buffer.clear()
            elif in_block and stripped:
                buffer.append(stripped)
    finally:
        fh.close()


# --- Lifecycle ---------------------------------------------------------------
@app.on_event("startup")
async def _on_startup() -> None:
    asyncio.create_task(tail_proc_file())


@app.get("/health")
async def health() -> dict:
    return {
        "status":   "ok",
        "clients":  len(clients),
        "tickers":  sorted(history.keys()),
        "file":     str(PROC_FILE),
        "exists":   PROC_FILE.exists(),
    }


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    clients.add(ws)
    try:
        # Replay short history so a fresh chart isn't blank.
        snapshot = {sym: list(buf) for sym, buf in history.items()}
        await ws.send_text(json.dumps({"type": "snapshot", "data": snapshot}))

        # Keep the socket alive; we don't expect inbound messages but drain them.
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        clients.discard(ws)
