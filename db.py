"""SQLite storage for trades + DuckDB for analytics."""
import hashlib
import sqlite3
from pathlib import Path

import duckdb
import pandas as pd

DB_PATH = Path(__file__).parent / "journal.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date TEXT NOT NULL,          -- YYYY-MM-DD
    trade_time TEXT,                   -- HH:MM:SS (optional, used for ordering/streaks)
    symbol TEXT NOT NULL,
    side TEXT,                         -- Long / Short
    qty REAL,
    entry_price REAL,
    exit_price REAL,
    fees REAL DEFAULT 0,
    pnl REAL NOT NULL,                 -- net PNL (after fees)
    strategy TEXT,
    notes TEXT,
    row_hash TEXT UNIQUE,              -- used to skip duplicate CSV imports (NULL while a trade is open)
    status TEXT NOT NULL DEFAULT 'closed',  -- 'open' trades are excluded from all PNL/analytics
    opened_at TEXT                     -- YYYY-MM-DD HH:MM:SS, set for trades added as open
);
CREATE INDEX IF NOT EXISTS idx_trades_date ON trades(trade_date);
"""

COLUMNS = ["trade_date", "trade_time", "symbol", "side", "qty", "entry_price", "exit_price",
           "fees", "pnl", "strategy", "notes"]


def conn():
    c = sqlite3.connect(DB_PATH)
    c.executescript(SCHEMA)
    have = {r[1] for r in c.execute("PRAGMA table_info(trades)")}  # migrate older DBs
    if "trade_time" not in have:
        c.execute("ALTER TABLE trades ADD COLUMN trade_time TEXT")
    if "status" not in have:
        c.execute("ALTER TABLE trades ADD COLUMN status TEXT NOT NULL DEFAULT 'closed'")
    if "opened_at" not in have:
        c.execute("ALTER TABLE trades ADD COLUMN opened_at TEXT")
    return c


def _clean(v):
    return None if pd.isna(v) else v


def calc_pnl(side, qty, entry, exit_, fees):
    if None in (qty, entry, exit_):
        return None
    direction = -1 if str(side).lower().startswith("s") else 1
    return (exit_ - entry) * qty * direction - (fees or 0)


def row_hash(row: dict) -> str:
    key = "|".join(str(row.get(c)) for c in COLUMNS)
    return hashlib.sha1(key.encode()).hexdigest()


def prepare(r: dict) -> dict:
    """Clean a raw row (NaN -> None) and add its row_hash."""
    r = {k: _clean(r.get(k)) for k in COLUMNS}
    r["row_hash"] = row_hash(r)
    return r


def insert_trades(rows):
    """Insert dict rows; returns (inserted, skipped_duplicates)."""
    ins = skip = 0
    with conn() as c:
        for r in rows:
            r = prepare(r)
            cur = c.execute(
                f"INSERT OR IGNORE INTO trades ({','.join(COLUMNS)},row_hash) "
                f"VALUES ({','.join('?' * (len(COLUMNS) + 1))})",
                [r[k] for k in COLUMNS] + [r["row_hash"]],
            )
            ins += cur.rowcount
            skip += 1 - cur.rowcount
    return ins, skip


def load_trades() -> pd.DataFrame:
    """Closed trades only; open trades never reach PNL/analytics."""
    with conn() as c:
        df = pd.read_sql(
            "SELECT * FROM trades WHERE status='closed' ORDER BY trade_date DESC, coalesce(trade_time, '') DESC, id DESC", c)
    return df.drop(columns=["status"])


def symbols() -> list:
    """Every symbol used so far (open and closed), so new ones appear in the picker automatically."""
    with conn() as c:
        return [r[0] for r in c.execute("SELECT DISTINCT symbol FROM trades ORDER BY symbol")]


def load_open_trades() -> pd.DataFrame:
    with conn() as c:
        return pd.read_sql("SELECT * FROM trades WHERE status='open' ORDER BY opened_at DESC, id DESC", c)


def insert_open_trade(opened_at: str, symbol, side, qty, entry, fees, strategy, notes):
    """Add a trade that is still running. pnl is a 0 placeholder (column is NOT NULL); row_hash is set on close."""
    with conn() as c:
        c.execute(
            "INSERT INTO trades (trade_date, symbol, side, qty, entry_price, fees, pnl, strategy, notes, status, opened_at) "
            "VALUES (?,?,?,?,?,?,0,?,?, 'open', ?)",
            [opened_at[:10], symbol, side, qty, entry, fees, strategy, notes, opened_at],
        )


def close_trade(trade_id, trade_date, trade_time, exit_price, fees, pnl):
    """Turn an open trade into a closed one. Raises sqlite3.IntegrityError if an identical trade already exists."""
    with conn() as c:
        row = dict(zip(COLUMNS, c.execute(f"SELECT {','.join(COLUMNS)} FROM trades WHERE id=?", [trade_id]).fetchone()))
        row.update(trade_date=trade_date, trade_time=trade_time, exit_price=exit_price, fees=fees, pnl=pnl)
        row = prepare(row)
        c.execute(
            "UPDATE trades SET trade_date=?, trade_time=?, exit_price=?, fees=?, pnl=?, status='closed', row_hash=? WHERE id=?",
            [trade_date, trade_time, exit_price, fees, pnl, row["row_hash"], trade_id],
        )


def delete_trades(ids):
    with conn() as c:
        c.executemany("DELETE FROM trades WHERE id=?", [(int(i),) for i in ids])


def update_trades(df: pd.DataFrame):
    """Persist edits made in the trades table (matched by id)."""
    with conn() as c:
        for r in df.to_dict("records"):
            c.execute(
                "UPDATE trades SET trade_date=?, trade_time=?, symbol=?, side=?, qty=?, entry_price=?, "
                "exit_price=?, fees=?, pnl=?, strategy=?, notes=? WHERE id=?",
                [_clean(r[k]) for k in COLUMNS] + [int(r["id"])],
            )


def analytics(sql: str, trades: pd.DataFrame) -> pd.DataFrame:
    """Run DuckDB SQL against the trades DataFrame (exposed as table `trades`)."""
    d = duckdb.connect()
    d.register("trades", trades)
    return d.execute(sql).df()


SUMMARY_SQL = """
SELECT count(*) AS trades,
       sum(qty) AS volume,
       avg(qty) AS avg_size,
       sum(pnl) AS total_pnl,
       avg(pnl) AS avg_pnl,
       100.0 * avg((pnl > 0)::INT) AS win_rate,
       avg(pnl) FILTER (pnl > 0) AS avg_win,
       avg(pnl) FILTER (pnl < 0) AS avg_loss,
       sum(pnl) FILTER (pnl > 0) / nullif(-sum(pnl) FILTER (pnl < 0), 0) AS profit_factor,
       max(pnl) AS best,
       min(pnl) AS worst
FROM trades
"""

BY_STRATEGY_SQL = """
SELECT coalesce(nullif(strategy, ''), '(none)') AS strategy,
       count(*) AS trades,
       sum(qty) AS volume,
       avg(qty) AS avg_size,
       sum(pnl) AS total_pnl,
       avg(pnl) AS avg_pnl,
       100.0 * avg((pnl > 0)::INT) AS win_rate,
       sum(pnl) FILTER (pnl > 0) / nullif(-sum(pnl) FILTER (pnl < 0), 0) AS profit_factor
FROM trades GROUP BY 1 ORDER BY total_pnl DESC
"""

BY_SYMBOL_SQL = BY_STRATEGY_SQL.replace("coalesce(nullif(strategy, ''), '(none)') AS strategy", "symbol")

BY_WEEKDAY_SQL = """
SELECT dayname(CAST(trade_date AS DATE)) AS weekday,
       count(*) AS trades, sum(qty) AS volume, avg(qty) AS avg_size, sum(pnl) AS total_pnl,
       100.0 * avg((pnl > 0)::INT) AS win_rate
FROM trades GROUP BY 1, isodow(CAST(trade_date AS DATE)) ORDER BY isodow(CAST(trade_date AS DATE))
"""

DAILY_SQL = """
SELECT CAST(trade_date AS DATE) AS day, sum(pnl) AS pnl, count(*) AS trades
FROM trades GROUP BY 1 ORDER BY 1
"""

BY_SIDE_SQL = BY_STRATEGY_SQL.replace("coalesce(nullif(strategy, ''), '(none)') AS strategy", "coalesce(nullif(side, ''), '(none)') AS side")

BEST_DAY_SQL = "SELECT CAST(trade_date AS DATE) AS day, sum(pnl) AS pnl, count(*) AS trades FROM trades GROUP BY 1 ORDER BY pnl {order} LIMIT 1"


def streaks(trades: pd.DataFrame) -> dict:
    """Longest win/loss runs in chronological order. Break-even trades end a run."""
    t = trades.assign(_t=trades["trade_time"].fillna("")).sort_values(["trade_date", "_t", "id"])
    out = {"win": (0, None, None), "loss": (0, None, None)}
    cur_kind, cur_len, cur_start = None, 0, None
    for r in t.itertuples():
        kind = "win" if r.pnl > 0 else "loss" if r.pnl < 0 else None
        if kind != cur_kind or kind is None:
            cur_kind, cur_len, cur_start = kind, 0, r.trade_date
        if kind:
            cur_len += 1
            if cur_len > out[kind][0]:
                out[kind] = (cur_len, cur_start, r.trade_date)
    out["current"] = (cur_kind, cur_len)
    return out

BY_MONTH_SQL = """
SELECT strftime(CAST(trade_date AS DATE), '%Y-%m') AS month,
       count(*) AS trades,
       count(DISTINCT trade_date) AS days,
       sum(qty) AS volume,
       avg(qty) AS avg_size,
       sum(pnl) AS total_pnl,
       avg(pnl) AS avg_pnl,
       100.0 * avg((pnl > 0)::INT) AS win_rate,
       sum(pnl) FILTER (pnl > 0) / nullif(-sum(pnl) FILTER (pnl < 0), 0) AS profit_factor
FROM trades GROUP BY 1 ORDER BY 1
"""
