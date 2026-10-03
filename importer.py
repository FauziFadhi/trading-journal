"""CSV loading (messy broker exports, e.g. MetaTrader) and conversion to journal rows."""
import csv
import io

import pandas as pd

import db

NON_TRADE_TYPES = {"balance", "credit", "deposit", "withdrawal", "correction", "bonus", "charge", "rebate", "commission"}


def load_csv(raw: bytes) -> pd.DataFrame:
    """Detect delimiter + header row, so reports with preamble lines still load."""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    lines = text.splitlines()
    delim = max(",;\t|", key=lambda d: sum(l.count(d) for l in lines))
    rows = list(csv.reader(lines, delimiter=delim))

    def looks_like_header(r):
        return len(r) >= 3 and sum(bool(c.strip()) for c in r) / len(r) >= 0.7

    start = next((i for i, r in enumerate(rows[:50]) if looks_like_header(r)), 0)
    header = [c.strip() for c in rows[start]]
    seen = {}
    for i, h in enumerate(header):  # unique names: Price, Price.1
        n = seen.get(h, 0)
        seen[h] = n + 1
        header[i] = h if n == 0 else f"{h}.{n}"

    data = []
    for r in rows[start + 1:]:
        if not any(c.strip() for c in r):
            break  # blank line ends the first table
        if not any(c.strip() for c in r[:2]):
            continue  # footer/total rows such as "Closed P/L: 311.87"
        data.append((r + [""] * len(header))[: len(header)])
    return pd.DataFrame(data, columns=header).replace("", pd.NA)


def _num(s):
    return pd.to_numeric(
        s.astype(str).str.replace(r"[,$\s]", "", regex=True).str.replace(r"^\((.*)\)$", r"-\1", regex=True),
        errors="coerce",
    )


def to_trades(df, mapping, dayfirst=False, default_strategy="", subtract_fees=False, src_tz=0, dst_tz=0):
    """Returns (clean DataFrame ready for db.insert_trades, mask of invalid rows, count of non-trade rows dropped)."""
    out = pd.DataFrame(index=df.index)
    for f in db.COLUMNS:
        c = mapping.get(f)
        out[f] = df[c] if c else None

    if mapping.get("side"):  # drop deposits etc., normalise buy/sell
        low = out["side"].astype(str).str.lower().str.strip()
        keep = ~low.isin(NON_TRADE_TYPES)
        out, df, low = out[keep], df[keep], low[keep]
        out["side"] = low.map(lambda s: "Long" if s[:1] in "bl" else "Short" if s[:1] == "s" else s.title())
    dropped = len(keep) - int(keep.sum()) if mapping.get("side") else 0

    dt = pd.to_datetime(out["trade_date"], dayfirst=dayfirst, errors="coerce")
    has_time = (dt.dropna() != dt.dropna().dt.normalize()).any()
    if has_time:  # shift broker time to journal timezone (may move the trade to another day)
        dt = dt + pd.Timedelta(hours=dst_tz - src_tz)
    out["trade_date"] = dt.dt.strftime("%Y-%m-%d")
    out["trade_time"] = dt.dt.strftime("%H:%M:%S") if has_time else None
    for f in ("qty", "entry_price", "exit_price", "fees", "pnl"):
        out[f] = _num(out[f])
    out["fees"] = out["fees"].fillna(0).abs()
    if default_strategy:
        out["strategy"] = out["strategy"].where(out["strategy"].notna(), default_strategy)
    missing = out["pnl"].isna()
    out.loc[missing, "pnl"] = [db.calc_pnl(r.side, r.qty, r.entry_price, r.exit_price, r.fees) for r in out[missing].itertuples()]
    if subtract_fees:
        out.loc[~missing, "pnl"] -= out.loc[~missing, "fees"]
    bad = out["trade_date"].isna() | out["symbol"].isna() | out["pnl"].isna()
    return out, bad, dropped


def _key(r):
    """Identity of a trade ignoring date/time (catches the same trade imported with another timezone)."""
    n = lambda v, p: None if pd.isna(v) else round(float(v), p)
    return (str(r["symbol"]).upper(), str(r["side"]), n(r["qty"], 6), n(r["entry_price"], 6), n(r["exit_price"], 6), n(r["pnl"], 2))


def classify(good: pd.DataFrame, existing: pd.DataFrame) -> pd.DataFrame:
    """Compare importable rows with the journal.

    status: 'exact' (identical row already saved, skipped automatically),
            'probable' (same trade values but different date/time, e.g. other timezone),
            'new'.
    match_id: id of the matching existing trade.
    """
    hashes = dict(zip(existing["row_hash"], existing["id"]))
    keys = {}
    for r in existing.to_dict("records"):
        keys.setdefault(_key(r), r["id"])
    status, match = [], []
    for r in good.to_dict("records"):
        h = db.prepare(r)["row_hash"]
        k = _key(r)
        if h in hashes:
            status.append("exact"), match.append(hashes[h])
        elif k in keys:
            status.append("probable"), match.append(keys[k])
        else:
            status.append("new"), match.append(None)
    return good.assign(status=status, match_id=match)
