"""
collect_binance_public_market_data.py
--------------------------------------
Binance Public Market Data Collector V1
- NO API key / secret required
- NO order / trading functionality
- Collects: trade stream + best bid/ask (bookTicker) via WebSocket
- REST fallback when WebSocket fails
- Appends to SQLite DB
- Records collector_runs summary on exit
"""

import argparse
import json
import os
import sqlite3
import sys
import time
import threading
import uuid
from datetime import datetime, timezone

try:
    import websocket  # websocket-client
    WS_AVAILABLE = True
except ImportError:
    WS_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────
DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "XRPUSDT", "DOGEUSDT", "SOLUSDT"]
DEFAULT_DURATION = 60          # seconds
DB_DIR = "logs/experiments/cross_market"
DB_PATH = os.path.join(DB_DIR, "binance_public_market_data.sqlite")

WS_BASE = "wss://stream.binance.com:9443/stream?streams="
REST_TICKER_URL = "https://api.binance.com/api/v3/ticker/bookTicker"
REST_TRADES_URL = "https://api.binance.com/api/v3/trades"

# ──────────────────────────────────────────────
# DB helpers
# ──────────────────────────────────────────────
def init_db(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS binance_events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            received_ts REAL,
            event_ts    REAL,
            symbol      TEXT,
            event_type  TEXT,
            price       REAL,
            qty         REAL,
            side        TEXT,
            best_bid    REAL,
            best_ask    REAL,
            bid_size    REAL,
            ask_size    REAL,
            raw_json    TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS collector_runs (
            run_id     TEXT PRIMARY KEY,
            started_at TEXT,
            ended_at   TEXT,
            symbols    TEXT,
            mode       TEXT,
            total_rows INTEGER,
            errors     INTEGER,
            notes      TEXT
        )
    """)
    conn.commit()
    return conn


def insert_event(conn: sqlite3.Connection, row: dict) -> None:
    conn.execute("""
        INSERT INTO binance_events
            (received_ts, event_ts, symbol, event_type, price, qty, side,
             best_bid, best_ask, bid_size, ask_size, raw_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        row.get("received_ts"), row.get("event_ts"), row.get("symbol"),
        row.get("event_type"), row.get("price"), row.get("qty"), row.get("side"),
        row.get("best_bid"), row.get("best_ask"), row.get("bid_size"),
        row.get("ask_size"), row.get("raw_json"),
    ))
    conn.commit()


def save_run(conn: sqlite3.Connection, run: dict) -> None:
    conn.execute("""
        INSERT OR REPLACE INTO collector_runs
            (run_id, started_at, ended_at, symbols, mode, total_rows, errors, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run["run_id"], run["started_at"], run["ended_at"],
        run["symbols"], run["mode"], run["total_rows"],
        run["errors"], run["notes"],
    ))
    conn.commit()


# ──────────────────────────────────────────────
# Payload parser
# ──────────────────────────────────────────────
def parse_ws_message(raw: str, received_ts: float) -> dict | None:
    """Parse combined stream message (trade or bookTicker)."""
    try:
        outer = json.loads(raw)
        data = outer.get("data", outer)
        etype = data.get("e", "")

        row = {
            "received_ts": received_ts,
            "event_ts": data.get("T", data.get("u", received_ts * 1000)) / 1000.0,
            "symbol": data.get("s", ""),
            "event_type": etype,
            "price": None, "qty": None, "side": None,
            "best_bid": None, "best_ask": None,
            "bid_size": None, "ask_size": None,
            "raw_json": raw,
        }

        if etype == "trade":
            row["price"] = float(data.get("p", 0))
            row["qty"] = float(data.get("q", 0))
            row["side"] = "BUY" if not data.get("m", True) else "SELL"

        elif etype == "bookTicker":
            row["best_bid"] = float(data.get("b", 0))
            row["best_ask"] = float(data.get("a", 0))
            row["bid_size"] = float(data.get("B", 0))
            row["ask_size"] = float(data.get("A", 0))
            row["event_ts"] = received_ts

        else:
            return None   # unsupported event

        return row
    except Exception:
        return None


# ──────────────────────────────────────────────
# WebSocket collector
# ──────────────────────────────────────────────
def run_websocket(
    symbols: list[str],
    conn: sqlite3.Connection,
    stop_event: threading.Event,
    counters: dict,
) -> None:
    streams = []
    for sym in symbols:
        s = sym.lower()
        streams.append(f"{s}@trade")
        streams.append(f"{s}@bookTicker")
    url = WS_BASE + "/".join(streams)

    def on_message(ws_app, message):
        ts = time.time()
        row = parse_ws_message(message, ts)
        if row and row["symbol"]:
            try:
                insert_event(conn, row)
                counters["rows"] += 1
            except Exception as e:
                counters["errors"] += 1
                print(f"[WS][DB_ERR] {e}", file=sys.stderr)

    def on_error(ws_app, error):
        counters["errors"] += 1
        print(f"[WS][ERR] {error}", file=sys.stderr)

    def on_close(ws_app, close_status_code, close_msg):
        print("[WS] Connection closed.", flush=True)

    def on_open(ws_app):
        print(f"[WS] Connected: {len(streams)} streams", flush=True)

    ws = websocket.WebSocketApp(
        url,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
        on_open=on_open,
    )

    def _run():
        ws.run_forever(ping_interval=20, ping_timeout=10)

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    stop_event.wait()
    ws.close()
    t.join(timeout=5)


# ──────────────────────────────────────────────
# REST fallback collector
# ──────────────────────────────────────────────
def run_rest(
    symbols: list[str],
    conn: sqlite3.Connection,
    stop_event: threading.Event,
    counters: dict,
    poll_interval: float = 1.5,
) -> None:
    if not REQUESTS_AVAILABLE:
        print("[REST] requests not installed.", file=sys.stderr)
        return

    print("[REST] Starting REST polling mode...", flush=True)
    while not stop_event.is_set():
        ts = time.time()
        for sym in symbols:
            try:
                r = requests.get(
                    REST_TICKER_URL, params={"symbol": sym}, timeout=5
                )
                if r.status_code == 200:
                    data = r.json()
                    row = {
                        "received_ts": ts,
                        "event_ts": ts,
                        "symbol": sym,
                        "event_type": "bookTicker_rest",
                        "price": None, "qty": None, "side": None,
                        "best_bid": float(data.get("bidPrice", 0)),
                        "best_ask": float(data.get("askPrice", 0)),
                        "bid_size": float(data.get("bidQty", 0)),
                        "ask_size": float(data.get("askQty", 0)),
                        "raw_json": r.text,
                    }
                    insert_event(conn, row)
                    counters["rows"] += 1
                else:
                    counters["errors"] += 1
            except Exception as e:
                counters["errors"] += 1
                print(f"[REST][ERR] {sym}: {e}", file=sys.stderr)

        stop_event.wait(poll_interval)


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Binance Public Market Data Collector (no API key required)"
    )
    parser.add_argument(
        "--symbols",
        default=",".join(DEFAULT_SYMBOLS),
        help="Comma-separated symbols, e.g. BTCUSDT,ETHUSDT",
    )
    parser.add_argument(
        "--duration-sec",
        type=int,
        default=DEFAULT_DURATION,
        help="Collection duration in seconds (default: 60)",
    )
    parser.add_argument(
        "--mode",
        choices=["ws", "rest", "auto"],
        default="auto",
        help="Collection mode: ws=WebSocket, rest=REST polling, auto=ws with rest fallback",
    )
    parser.add_argument(
        "--db",
        default=DB_PATH,
        help=f"SQLite output path (default: {DB_PATH})",
    )
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    if not symbols:
        print("No symbols specified.", file=sys.stderr)
        sys.exit(1)

    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()
    print(f"[INIT] run_id={run_id}")
    print(f"[INIT] symbols={symbols}")
    print(f"[INIT] mode={args.mode}, duration={args.duration_sec}s, db={args.db}")

    conn = init_db(args.db)
    stop_event = threading.Event()
    counters = {"rows": 0, "errors": 0}
    mode_used = args.mode

    use_ws = args.mode in ("ws", "auto") and WS_AVAILABLE
    use_rest = args.mode == "rest" or (args.mode == "auto" and not WS_AVAILABLE)

    if use_ws:
        mode_used = "ws"
        t = threading.Thread(
            target=run_websocket,
            args=(symbols, conn, stop_event, counters),
            daemon=True,
        )
        t.start()
    elif use_rest:
        mode_used = "rest"
        t = threading.Thread(
            target=run_rest,
            args=(symbols, conn, stop_event, counters),
            daemon=True,
        )
        t.start()
    else:
        print("[WARN] Neither ws nor rest mode available. Exiting.", file=sys.stderr)
        sys.exit(1)

    print(f"[RUN] Collecting for {args.duration_sec}s ...", flush=True)
    try:
        time.sleep(args.duration_sec)
    except KeyboardInterrupt:
        print("[RUN] Interrupted by user.")

    stop_event.set()

    ended_at = datetime.now(timezone.utc).isoformat()
    run_summary = {
        "run_id": run_id,
        "started_at": started_at,
        "ended_at": ended_at,
        "symbols": ",".join(symbols),
        "mode": mode_used,
        "total_rows": counters["rows"],
        "errors": counters["errors"],
        "notes": f"duration_sec={args.duration_sec}",
    }
    save_run(conn, run_summary)
    conn.close()

    print(
        f"[DONE] rows={counters['rows']} errors={counters['errors']} "
        f"mode={mode_used} db={args.db}"
    )
    print(json.dumps(run_summary, indent=2))


if __name__ == "__main__":
    main()
