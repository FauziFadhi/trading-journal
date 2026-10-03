import calendar
import json
import os
import signal
import sqlite3
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

import db
import importer

st.set_page_config(page_title="Trading Journal", layout="wide")

MAPPINGS_FILE = Path(__file__).parent / "csv_mappings.json"

# Target field -> lowercase header names we auto-match
ALIASES = {
    "trade_date": ["date", "trade date", "trade_date", "time", "datetime", "close time", "exit time", "closed", "date/time"],
    "symbol": ["symbol", "item", "ticker", "instrument", "asset", "pair", "contract"],
    "side": ["side", "direction", "type", "action", "buy/sell"],
    "qty": ["qty", "quantity", "size", "shares", "contracts", "volume", "lots"],
    "entry_price": ["entry", "price", "entry price", "entry_price", "open price", "buy price", "avg entry"],
    "exit_price": ["exit", "price.1", "exit price", "exit_price", "close price", "sell price", "avg exit"],
    "fees": ["fees", "fee", "commission", "commissions", "comm"],
    "pnl": ["pnl", "p&l", "p/l", "profit", "net pnl", "realized pnl", "net p&l", "profit/loss", "gain/loss"],
    "strategy": ["strategy", "setup", "tag", "tags"],
    "notes": ["notes", "note", "comment", "comments", "description"],
}
LABELS = {
    "trade_date": "Date *", "trade_time": "(time is read from the date column)", "symbol": "Symbol *", "side": "Side (Long/Short)",
    "qty": "Quantity", "entry_price": "Entry price", "exit_price": "Exit price",
    "fees": "Fees / commission", "pnl": "PNL (if blank, computed from prices)",
    "strategy": "Strategy", "notes": "Notes",
}


def money(v):
    return "-" if v is None or pd.isna(v) else f"{v:,.2f}"


# ---------------------------------------------------------------- Calendar
def page_calendar(trades):
    today = date.today()
    c1, c2, _ = st.columns([1, 1, 4])
    year = c1.number_input("Year", 2000, 2100, today.year)
    month = c2.selectbox("Month", range(1, 13), today.month - 1, format_func=lambda m: calendar.month_name[m])

    t = trades.copy()
    t["d"] = pd.to_datetime(t["trade_date"]).dt.date
    month_t = t[(pd.to_datetime(t["trade_date"]).dt.year == year) & (pd.to_datetime(t["trade_date"]).dt.month == month)]
    daily = month_t.groupby("d")["pnl"].agg(["sum", "count"])

    n_open = len(db.load_open_trades())
    if n_open:
        st.info(f"{n_open} open trade{'s' if n_open > 1 else ''} not counted yet. Close them on the Trades page.")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Month PNL", money(month_t["pnl"].sum()))
    m2.metric("Trades", len(month_t))
    m3.metric("Win rate", f"{(month_t['pnl'] > 0).mean() * 100:.0f}%" if len(month_t) else "-")
    m4.metric("Trading days", len(daily))

    sel = st.session_state.get("sel_day")
    if sel and (sel.year, sel.month) != (year, month):
        sel = st.session_state.sel_day = None

    # Each day is a button; per-day colours are applied through the st-key-<key> CSS class.
    css = [
        "[class*='st-key-day_'] button{min-height:84px;align-items:flex-start;justify-content:flex-start;text-align:left;"
        "border:1px solid rgba(128,128,128,.25);background:transparent;padding:6px 8px}",
        "[class*='st-key-day_'] button p{white-space:pre-line;font-size:.85em;line-height:1.3;text-align:left}",
        ".wk{height:84px;display:flex;align-items:center;justify-content:center;font-weight:700;border:1px dashed rgba(128,128,128,.3);border-radius:8px}",
        ".wk.win{color:#26a65b;background:rgba(38,166,91,.12)} .wk.loss{color:#e74c3c;background:rgba(231,76,60,.12)}",
        ".dow{text-align:center;opacity:.7;font-size:.85em}",
    ]
    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdatescalendar(year, month)
    clicked = None
    for i, name in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun", "Week"]):
        if i == 0:
            hdr = st.columns(8)
        hdr[i].markdown(f"<div class='dow'>{name}</div>", unsafe_allow_html=True)
    for week in weeks:
        cols, wk = st.columns(8), 0.0
        for col, d in zip(cols, week):
            if d.month != month:
                continue
            if d in daily.index:
                p, n = daily.loc[d, "sum"], int(daily.loc[d, "count"])
                wk += p
                label = f"{d.day}  \n**{p:+,.2f}**  \n{n} trade{'s' if n > 1 else ''}"
                bg = "38,166,91" if p > 0 else "231,76,60" if p < 0 else "128,128,128"
                css.append(f".st-key-day_{d} button{{background:rgba({bg},.25)}}")
            else:
                label = str(d.day)
            if d == sel:
                css.append(f".st-key-day_{d} button{{outline:3px solid #4c8bf5;outline-offset:-3px}}")
            if col.button(label, key=f"day_{d}", width="stretch"):
                clicked = d
        wcls = "win" if wk > 0 else "loss" if wk < 0 else ""
        cols[7].markdown(f"<div class='wk {wcls}'>{wk:+,.2f}</div>", unsafe_allow_html=True)
    st.markdown(f"<style>{''.join(css)}</style>", unsafe_allow_html=True)

    if clicked:
        st.session_state.sel_day = clicked
        st.rerun()

    if sel:
        day_t = month_t[month_t["d"] == sel]
        if day_t.empty:
            st.info(f"{sel:%A, %d %B %Y}: no trades.")
        else:
            total = day_t["pnl"].sum()
            tc = "#26a65b" if total > 0 else "#e74c3c" if total < 0 else "inherit"
            st.markdown(
                f"### {sel:%A, %d %B %Y}: <span style='color:{tc}'>{total:+,.2f}</span> ({len(day_t)} trades · volume {day_t['qty'].sum():,.2f})",
                unsafe_allow_html=True,
            )
            st.dataframe(
                day_t.drop(columns=["d", "row_hash"]).style.format({"pnl": "{:+,.2f}"})
                .map(pnl_color, subset=["pnl"]).map(side_color, subset=["side"]),
                hide_index=True, width="stretch",
            )
    else:
        st.caption("Click a date to see its trades.")


# ---------------------------------------------------------------- Add trade
def symbol_input(col):
    """Pick an existing symbol or type a new one (it is saved with the trade, so it shows up next time)."""
    known = db.symbols()
    val = col.selectbox("Symbol", known, index=None, accept_new_options=True, placeholder="Pick or type a new one")
    if not val:
        return ""
    val = val.strip()
    return next((k for k in known if k.upper() == val.upper()), val.upper())  # reuse existing spelling (e.g. BTCUSD.Daily)


def strategy_inputs():
    existing = db.load_trades()["strategy"].dropna().unique().tolist()
    s1, s2 = st.columns(2)
    pick = s1.selectbox("Strategy", [""] + sorted(existing))
    new = s2.text_input("...or new strategy")
    return new.strip() or pick


def page_add():
    st.subheader("Add trade")
    status = st.radio("Status", ["Closed", "Open (still running)"], horizontal=True)
    if status == "Closed":
        with st.form("add", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            d = c1.date_input("Date", date.today())
            symbol = symbol_input(c2)
            side = c3.selectbox("Side", ["Long", "Short"])
            c1, c2, c3, c4 = st.columns(4)
            qty = c1.number_input("Quantity", min_value=0.0, value=0.0, format="%.4f")
            entry = c2.number_input("Entry price", min_value=0.0, value=0.0, format="%.4f")
            exit_ = c3.number_input("Exit price", min_value=0.0, value=0.0, format="%.4f")
            fees = c4.number_input("Fees", min_value=0.0, value=0.0, format="%.2f")
            pnl_in = st.text_input("PNL override (optional, net of fees; leave blank to compute)")
            strategy = strategy_inputs()
            notes = st.text_area("Notes / reasoning / lessons")
            if st.form_submit_button("Save trade", type="primary"):
                pnl = float(pnl_in) if pnl_in.strip() else db.calc_pnl(side, qty, entry, exit_, fees)
                if not symbol or pnl is None:
                    st.error("Symbol is required, plus either a PNL or qty/entry/exit prices.")
                else:
                    db.insert_trades([dict(trade_date=d.isoformat(), symbol=symbol, side=side, qty=qty, entry_price=entry,
                                           exit_price=exit_, fees=fees, pnl=pnl, strategy=strategy, notes=notes)])
                    st.success(f"Saved {symbol}: PNL {pnl:,.2f}")
    else:
        st.caption("Open trades are not counted in PNL, the calendar or analytics until you close them on the Trades page.")
        with st.form("add_open", clear_on_submit=True):
            c1, c2, c3, c4 = st.columns(4)
            d = c1.date_input("Opened on", date.today())
            t = c2.time_input("Opened at", datetime.now().time().replace(second=0, microsecond=0))
            symbol = symbol_input(c3)
            side = c4.selectbox("Side", ["Long", "Short"])
            c1, c2, c3 = st.columns(3)
            qty = c1.number_input("Quantity", min_value=0.0, value=0.0, format="%.4f")
            entry = c2.number_input("Entry price", min_value=0.0, value=0.0, format="%.4f")
            fees = c3.number_input("Fees so far", min_value=0.0, value=0.0, format="%.2f")
            strategy = strategy_inputs()
            notes = st.text_area("Notes / plan (entry reason, stop, target)")
            if st.form_submit_button("Save open trade", type="primary"):
                if not symbol:
                    st.error("Symbol is required.")
                else:
                    db.insert_open_trade(datetime.combine(d, t).strftime("%Y-%m-%d %H:%M:%S"), symbol, side, qty, entry,
                                         fees, strategy, notes)
                    st.success(f"Saved open {side} {symbol}. Close it later from the Trades page.")


# ---------------------------------------------------------------- Trades
def open_trades_section():
    op = db.load_open_trades()
    if op.empty:
        return
    st.subheader(f"Open trades ({len(op)})")
    st.caption("Not counted in PNL, calendar or analytics until closed.")
    for r in op.itertuples():
        title = f"{r.symbol} {r.side} · qty {r.qty:g} @ {r.entry_price:g} · opened {r.opened_at}"
        with st.expander(title):
            if r.notes:
                st.write(r.notes)
            c1, c2, c3, c4 = st.columns(4)
            now = datetime.now()
            exit_ = c1.number_input("Exit price", min_value=0.0, value=0.0, format="%.4f", key=f"x_{r.id}")
            fees = c2.number_input("Total fees", min_value=0.0, value=float(r.fees or 0), format="%.2f", key=f"f_{r.id}")
            cd = c3.date_input("Closed on", now.date(), key=f"cd_{r.id}")
            ct = c4.time_input("Closed at", now.time().replace(second=0, microsecond=0), key=f"ct_{r.id}")
            pnl_in = st.text_input("PNL override (optional, net of fees)", key=f"p_{r.id}")
            b1, b2, _ = st.columns([1, 1, 4])
            if b1.button("Close trade", type="primary", key=f"close_{r.id}"):
                pnl = float(pnl_in) if pnl_in.strip() else db.calc_pnl(r.side, r.qty, r.entry_price, exit_, fees)
                if pnl is None or (not pnl_in.strip() and exit_ == 0):
                    st.error("Enter an exit price (or a PNL override).")
                else:
                    try:
                        db.close_trade(r.id, cd.isoformat(), ct.strftime("%H:%M:%S"), exit_, fees, pnl)
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("An identical closed trade already exists.")
            if b2.button("Delete", key=f"del_{r.id}"):
                db.delete_trades([r.id])
                st.rerun()


def page_trades(trades):
    open_trades_section()
    st.subheader("All trades")
    if trades.empty:
        st.info("No trades yet.")
        return
    f1, f2 = st.columns(2)
    sym = f1.multiselect("Symbol", sorted(trades["symbol"].unique()))
    strat = f2.multiselect("Strategy", sorted(trades["strategy"].dropna().unique()))
    v = trades
    if sym:
        v = v[v["symbol"].isin(sym)]
    if strat:
        v = v[v["strategy"].isin(strat)]
    v = v.drop(columns=["row_hash"]).copy()
    v.insert(0, "delete", False)
    edited = st.data_editor(v, hide_index=True, width="stretch", disabled=["id", "opened_at"], key="editor")
    c1, c2, _ = st.columns([1, 1, 4])
    if c1.button("Save edits"):
        db.update_trades(edited.drop(columns=["delete"]))
        st.rerun()
    if c2.button("Delete checked"):
        ids = edited.loc[edited["delete"], "id"]
        if len(ids):
            db.delete_trades(ids)
            st.rerun()


# ---------------------------------------------------------------- Import
def guess(field, cols):
    low = {c.lower().strip(): c for c in cols}
    for a in ALIASES[field]:
        if a in low:
            return low[a]
    return None


def page_import():
    st.subheader("Import CSV")
    up = st.file_uploader("CSV file", type=["csv", "txt"])
    if not up:
        return
    df = importer.load_csv(up.getvalue())
    st.caption(f"{len(df)} rows, {len(df.columns)} columns (delimiter and header row detected automatically)")
    st.dataframe(df.head(5), width="stretch", hide_index=True)

    cols = list(df.columns)
    sig = "|".join(sorted(map(str, cols)))
    saved = json.loads(MAPPINGS_FILE.read_text()) if MAPPINGS_FILE.exists() else {}
    prev = saved.get(sig, {})

    st.markdown("**Match your CSV columns to journal fields**")
    mapping = {}
    grid = st.columns(2)
    fields = [f for f in db.COLUMNS if f != "trade_time"]
    for i, f in enumerate(fields):
        default = prev.get(f) if prev.get(f) in cols else guess(f, cols)
        opts = ["(skip)"] + cols
        idx = opts.index(default) if default in opts else 0
        pick = grid[i % 2].selectbox(LABELS[f], opts, idx, key=f"map_{f}")
        mapping[f] = None if pick == "(skip)" else pick

    o1, o2, o3 = st.columns(3)
    dayfirst = o1.checkbox("Dates are day-first (31/12/2026)")
    subtract_fees = o2.checkbox("PNL column is gross: subtract fees from it")
    default_strategy = o3.text_input("Default strategy for rows without one")
    z1, z2, _ = st.columns([1, 1, 2])
    src_tz = z1.number_input("CSV timezone (GMT+)", -12.0, 14.0, 3.0, 0.5, help="Broker server time in the file")
    dst_tz = z2.number_input("Journal timezone (GMT+)", -12.0, 14.0, 7.0, 0.5, help="Times are converted to this before saving")

    if not mapping["trade_date"] or not mapping["symbol"]:
        st.error("Date and Symbol must be mapped.")
        return
    if not mapping["pnl"] and not all(mapping[k] for k in ("qty", "entry_price", "exit_price")):
        st.error("Map PNL, or map Quantity + Entry + Exit so PNL can be computed.")
        return

    out, bad, dropped = importer.to_trades(df, mapping, dayfirst, default_strategy, subtract_fees, src_tz, dst_tz)
    existing = db.load_trades()
    cls = importer.classify(out[~bad], existing)
    counts = cls["status"].value_counts()

    st.markdown("**Overlap check against your journal**")
    if len(cls):
        st.caption(
            f"File: {cls['trade_date'].min()} to {cls['trade_date'].max()}"
            + (f" | Journal: {existing['trade_date'].min()} to {existing['trade_date'].max()}" if len(existing) else " | Journal is empty")
        )
    k = st.columns(4)
    k[0].metric("New trades", int(counts.get("new", 0)))
    k[1].metric("Exact duplicates", int(counts.get("exact", 0)), help="Identical row already saved. Always skipped.")
    k[2].metric("Probable duplicates", int(counts.get("probable", 0)),
                help="Same pair/side/size/prices/PNL as a saved trade but a different date or time (often a timezone difference).")
    k[3].metric("Invalid / non-trade rows", f"{int(bad.sum())} / {dropped}")

    overlap = cls[cls["status"] != "new"]
    if len(overlap):
        with st.expander(f"Show the {len(overlap)} overlapping rows"):
            ex = existing.set_index("id")
            view = overlap[["status", "match_id", "trade_date", "trade_time", "symbol", "side", "qty", "pnl"]].copy()
            view["saved_date"] = view["match_id"].map(ex["trade_date"])
            view["saved_time"] = view["match_id"].map(ex["trade_time"])
            st.dataframe(view.rename(columns={"match_id": "saved_id", "trade_date": "file_date", "trade_time": "file_time"}),
                         hide_index=True, width="stretch")

    mode = "skip"
    if counts.get("probable", 0):
        mode = st.radio(
            "Probable duplicates",
            ["skip", "import anyway", "replace saved trades"],
            horizontal=True,
            help="'replace' deletes the matching saved trades and imports the file's version (use after fixing a timezone).",
        )

    if st.button("Import", type="primary"):
        keep = cls[(cls["status"] == "new") | ((cls["status"] == "probable") & (mode != "skip"))]
        if mode == "replace saved trades":
            db.delete_trades(cls.loc[cls["status"] == "probable", "match_id"].unique())
        ins, dup = db.insert_trades(keep.drop(columns=["status", "match_id"]).to_dict("records"))

        saved[sig] = {k: v for k, v in mapping.items() if v}
        MAPPINGS_FILE.write_text(json.dumps(saved, indent=2))
        skipped = f"{int(counts.get('exact', 0))} exact duplicates"
        if mode == "skip":
            skipped += f" and {int(counts.get('probable', 0))} probable duplicates"
        st.success(
            f"Imported {ins} trades. Skipped {skipped}, {int(bad.sum())} invalid rows and "
            f"{dropped} non-trade rows. Mapping remembered for this CSV format."
        )
        if bad.any():
            st.dataframe(df.loc[bad[bad].index], hide_index=True)


# ---------------------------------------------------------------- Analytics
SIDE_COLORS = {"long": "#3b82f6", "short": "#f59e0b"}  # blue / amber, distinct from the green/red PNL colors


def side_color(v):
    c = SIDE_COLORS.get(str(v).lower())
    return f"color: {c}; font-weight: 700" if c else ""


def side_tag(v):
    c = SIDE_COLORS.get(str(v).lower())
    return f"<span style='color:{c};font-weight:700'>{v}</span>" if c else (v or "")


def pnl_color(v):
    return "color: #26a65b; font-weight: 600" if v > 0 else "color: #e74c3c; font-weight: 600" if v < 0 else ""


def week_label(monday):
    sunday = monday + pd.Timedelta(days=6)
    return f"{monday:%d %b} - {sunday:%d %b %Y}"


def page_analytics(trades):
    st.subheader("Performance (DuckDB)")
    if trades.empty:
        st.info("No trades yet.")
        return

    dates = pd.to_datetime(trades["trade_date"])
    f1, f2, f3, f4 = st.columns([1.2, 2, 2, 1.3])
    period = f1.radio("Period", ["All time", "Week", "Date range"])
    if period == "Week":
        mondays = sorted({pd.Timestamp(m) for m in (dates - pd.to_timedelta(dates.dt.weekday, unit="D")).dt.normalize()}, reverse=True)
        mon = f2.selectbox("Week", mondays, format_func=week_label)
        trades = trades[(dates >= mon) & (dates < mon + pd.Timedelta(days=7))]
    elif period == "Date range":
        r = f2.date_input("Range", (dates.min().date(), dates.max().date()))
        if len(r) == 2:
            trades = trades[(dates >= pd.Timestamp(r[0])) & (dates <= pd.Timestamp(r[1]))]
    pairs = f3.multiselect("Pair", sorted(trades["symbol"].unique()))
    sides = f4.multiselect("Side", sorted(trades["side"].dropna().unique()))
    if pairs:
        trades = trades[trades["symbol"].isin(pairs)]
    if sides:
        trades = trades[trades["side"].isin(sides)]
    if trades.empty:
        st.info("No trades match these filters.")
        return

    s = db.analytics(db.SUMMARY_SQL, trades).iloc[0]
    cols = st.columns(5)
    cols[0].metric("Total PNL", money(s.total_pnl))
    cols[1].metric("Trades", int(s.trades))
    cols[2].metric("Win rate", f"{s.win_rate:.1f}%")
    cols[3].metric("Profit factor", money(s.profit_factor))
    cols[4].metric("Avg PNL", money(s.avg_pnl))
    cols = st.columns(4)
    cols[0].metric("Avg win", money(s.avg_win))
    cols[1].metric("Avg loss", money(s.avg_loss))
    cols[2].metric("Total volume", money(s.volume))
    cols[3].metric("Avg size", money(s.avg_size))

    st.markdown("**Highlights**")
    hi, lo = trades.loc[trades["pnl"].idxmax()], trades.loc[trades["pnl"].idxmin()]
    best_day = db.analytics(db.BEST_DAY_SQL.format(order="DESC"), trades).iloc[0]
    worst_day = db.analytics(db.BEST_DAY_SQL.format(order="ASC"), trades).iloc[0]
    k = db.streaks(trades)
    cur_kind, cur_n = k["current"]
    cards = [
        ("Highest profit", money(hi.pnl), f"{hi.symbol} {side_tag(hi.side)} · size {money(hi.qty)} · {hi.trade_date}", "win"),
        ("Biggest loss", money(lo.pnl), f"{lo.symbol} {side_tag(lo.side)} · size {money(lo.qty)} · {lo.trade_date}", "loss"),
        ("Best day", money(best_day.pnl), f"{best_day.day:%Y-%m-%d} · {int(best_day.trades)} trades", "win"),
        ("Worst day", money(worst_day.pnl), f"{worst_day.day:%Y-%m-%d} · {int(worst_day.trades)} trades", "loss"),
        ("Longest win streak", f"{k['win'][0]} wins", f"{k['win'][1]} to {k['win'][2]}" if k["win"][0] else "-", "win"),
        ("Longest loss streak", f"{k['loss'][0]} losses", f"{k['loss'][1]} to {k['loss'][2]}" if k["loss"][0] else "-", "loss"),
        ("Current streak", f"{cur_n} {cur_kind}{'s' if cur_n > 1 else ''}" if cur_kind else "-", "latest trades", cur_kind or "flat"),
    ]
    html = "".join(
        f"<div class='hl {cls}'><div class='t'>{t}</div><div class='v'>{v}</div><div class='s'>{sub}</div></div>"
        for t, v, sub, cls in cards
    )
    st.markdown(
        """<style>
        .hlgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin-bottom:1rem}
        .hl{border-radius:10px;padding:12px 14px;border-left:6px solid #888;background:rgba(128,128,128,.12)}
        .hl.win{background:rgba(38,166,91,.2);border-color:#26a65b} .hl.win .v{color:#26a65b}
        .hl.loss{background:rgba(231,76,60,.2);border-color:#e74c3c} .hl.loss .v{color:#e74c3c}
        .hl .t{font-size:.8em;opacity:.75;text-transform:uppercase;letter-spacing:.04em}
        .hl .v{font-size:1.7em;font-weight:800;line-height:1.3} .hl .s{font-size:.8em;opacity:.75}
        </style>"""
        f"<div class='hlgrid'>{html}</div>",
        unsafe_allow_html=True,
    )

    fmt = {"total_pnl": "{:,.2f}", "avg_pnl": "{:,.2f}", "win_rate": "{:.1f}%", "profit_factor": "{:.2f}", "volume": "{:,.2f}", "avg_size": "{:,.2f}"}
    for title, sql in [
        ("By pair", db.BY_SYMBOL_SQL), ("By side (buy / sell)", db.BY_SIDE_SQL),
        ("By strategy", db.BY_STRATEGY_SQL), ("By weekday", db.BY_WEEKDAY_SQL),
    ]:
        st.markdown(f"**{title}**")
        tbl = db.analytics(sql, trades)
        st.dataframe(
            tbl.style.format(fmt, na_rep="-").map(pnl_color, subset=[c for c in ("total_pnl", "avg_pnl") if c in tbl])
            .map(side_color, subset=[c for c in ("side",) if c in tbl]),
            hide_index=True, width="stretch",
        )

    with st.expander("Custom SQL (table: trades, uses the filters above)"):
        q = st.text_area("Query", "SELECT * FROM trades ORDER BY pnl DESC LIMIT 10")
        try:
            st.dataframe(db.analytics(q, trades), hide_index=True, width="stretch")
        except Exception as e:
            st.error(e)


def page_monthly(trades):
    st.subheader("Monthly view")
    if trades.empty:
        st.info("No trades yet.")
        return
    m = db.analytics(db.BY_MONTH_SQL, trades)
    m["cumulative"] = m["total_pnl"].cumsum()
    years = sorted({int(x[:4]) for x in m["month"]}, reverse=True)
    year = st.selectbox("Year", years)
    ym = m[m["month"].str.startswith(str(year))].set_index("month")

    c = st.columns(3)
    c[0].metric(f"{year} PNL", money(ym["total_pnl"].sum()))
    c[1].metric("Trades", int(ym["trades"].sum()))
    c[2].metric("Profitable months", f"{(ym['total_pnl'] > 0).sum()} / {len(ym)}")

    cards = ""
    for i in range(1, 13):
        key = f"{year}-{i:02d}"
        name = calendar.month_abbr[i]
        if key in ym.index:
            r = ym.loc[key]
            cls = "win" if r.total_pnl > 0 else "loss" if r.total_pnl < 0 else "flat"
            cards += (f"<div class='mc {cls}'><div class='t'>{name}</div><div class='v'>{r.total_pnl:+,.2f}</div>"
                      f"<div class='s'>{int(r.trades)} trades · {r.win_rate:.0f}% win</div>"
                      f"<div class='s'>volume {r.volume:,.2f}</div></div>")
        else:
            cards += f"<div class='mc'><div class='t'>{name}</div><div class='v'>-</div><div class='s'>no trades</div></div>"
    st.markdown(
        """<style>
        .mgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:.5rem 0 1rem}
        .mc{border-radius:10px;padding:12px 14px;border-left:6px solid #888;background:rgba(128,128,128,.1);opacity:.6}
        .mc.win{background:rgba(38,166,91,.2);border-color:#26a65b;opacity:1} .mc.win .v{color:#26a65b}
        .mc.loss{background:rgba(231,76,60,.2);border-color:#e74c3c;opacity:1} .mc.loss .v{color:#e74c3c}
        .mc .t{font-size:.8em;text-transform:uppercase;letter-spacing:.04em;opacity:.75}
        .mc .v{font-size:1.6em;font-weight:800;line-height:1.3} .mc .s{font-size:.8em;opacity:.75}
        </style>"""
        f"<div class='mgrid'>{cards}</div>",
        unsafe_allow_html=True,
    )

    st.markdown("**All months**")
    fmt = {"total_pnl": "{:,.2f}", "avg_pnl": "{:,.2f}", "win_rate": "{:.1f}%", "profit_factor": "{:.2f}", "volume": "{:,.2f}", "avg_size": "{:,.2f}", "cumulative": "{:,.2f}"}
    st.dataframe(
        m.iloc[::-1].style.format(fmt, na_rep="-").map(pnl_color, subset=["total_pnl", "avg_pnl", "cumulative"]),
        hide_index=True, width="stretch",
    )


# ---------------------------------------------------------------- Main
page = st.sidebar.radio("Journal", ["Calendar", "Monthly", "Add trade", "Trades", "Import CSV", "Analytics"])
st.sidebar.divider()
if st.sidebar.button("Shut down server"):
    st.session_state.confirm_quit = True
if st.session_state.get("confirm_quit"):
    st.sidebar.warning("Stop the server? You'll need ./run.sh to start it again.")
    q1, q2 = st.sidebar.columns(2)
    if q1.button("Yes, stop"):
        st.sidebar.success("Server stopped. You can close this tab.")
        os.kill(os.getpid(), signal.SIGTERM)
    if q2.button("Cancel"):
        st.session_state.confirm_quit = False
        st.rerun()
trades = db.load_trades()
if page == "Calendar":
    page_calendar(trades)
elif page == "Monthly":
    page_monthly(trades)
elif page == "Add trade":
    page_add()
elif page == "Trades":
    page_trades(trades)
elif page == "Import CSV":
    page_import()
else:
    page_analytics(trades)
