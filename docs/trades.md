# Trades (page "Trades")

`page_trades`.

## Open trades section (top of page, only if any exist)
`open_trades_section`: one expander per open trade (symbol, side, qty @ entry, opened time, notes). Inputs: exit price, total fees (prefilled), closed date/time (default now), optional PNL override. **Close trade** computes PNL with `calc_pnl` (or the override) and calls `db.close_trade`, which sets `status='closed'`, the close date/time, exit, fees, pnl and computes `row_hash`; an `IntegrityError` (identical closed trade exists) is shown as an error. **Delete** removes the open trade. Requires an exit price or PNL override.

## All trades table
Filters: symbol and strategy multiselects.

`st.data_editor` over the filtered trades with an extra `delete` checkbox column; `id` is read-only.
- "Save edits" calls `db.update_trades` for the visible rows (edited values persisted by `id`), then reruns.
- "Delete checked" calls `db.delete_trades` for checked ids.
Editable tables cannot show per-cell colors, so PNL is uncolored here (colored versions exist in the day detail and analytics tables).
Use this page to delete rows before re-importing with different settings (see import doc).

## Related
- [database.md](database.md): `update_trades`, `delete_trades`, and the `row_hash` caveat on edits
- [import-csv.md](import-csv.md): delete rows here before re-importing with new timezone settings
- [add-trade.md](add-trade.md): creating trades
- [calendar.md](calendar.md), [analytics.md](analytics.md): colored read-only views of the same data
