# Add trade (page "Add trade")

`page_add`. A **Status** radio (outside the forms, since forms cannot have conditional widgets) switches between two `st.form`s (both clear on submit).

Symbol field (both forms): `symbol_input()` is a `st.selectbox(..., accept_new_options=True)` listing `db.symbols()` (every symbol in the DB, open or closed). Pick one or type a new one; a new symbol is saved with the trade and appears in the list next time (no separate symbol table). Typed text is matched case-insensitively to an existing symbol (keeps e.g. `BTCUSD.Daily` spelling), otherwise uppercased.

## Closed trade form

Fields: date (default today), symbol (picker above), side Long/Short, quantity, entry, exit, fees, optional PNL override (text), strategy (dropdown of existing strategies or "new strategy" text, new wins), notes.

PNL = override if given, else `db.calc_pnl(...)` (net of fees). Error if symbol is empty or PNL cannot be computed (zero prices still compute to a number, so fill prices or override).

## Open trade form ("Open (still running)")
Fields: opened date + time, symbol, side, quantity, entry price, fees so far, strategy, notes/plan. No exit or PNL. Saved with `db.insert_open_trade` (`status='open'`, `opened_at`, `pnl=0` placeholder, `row_hash` NULL). Open trades are invisible to every PNL/analytics/calendar number; they are closed on the Trades page (see trades.md).

Limitations (closed form): no time field, so manual trades have `trade_time` NULL and sort after timed trades of the same day in streaks. Stored as-is in the journal timezone (no conversion).

## Related
- [trades.md](trades.md): edit a manual trade afterwards (e.g. fix PNL)
- [database.md](database.md): schema and `calc_pnl`
- [analytics.md](analytics.md): streak ordering when `trade_time` is missing
- [import-csv.md](import-csv.md): bulk alternative
