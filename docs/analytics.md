# Analytics (page "Analytics")

`page_analytics`. Everything is computed by DuckDB over the *filtered* DataFrame (`db.analytics`).

## Filters
Period radio: All time / Week (select among weeks present, Mon to Sun, label `15 Jun - 21 Jun 2026`) / Date range (date_input range). Plus Pair and Side multiselects.

## Metrics
Total PNL, trades, win rate, profit factor, avg PNL, avg win, avg loss, total volume, avg size (volume/size = `qty`, lots for MT).

## Highlights (colored cards, HTML `.hl`)
Highest profit trade, biggest loss trade (both show size), best day, worst day (daily sums), longest win streak, longest loss streak (with date range), current streak. Green for profit items, red for loss items.

## Streaks (`db.streaks`)
Order by `trade_date`, `trade_time` (NULL as ''), `id`. pnl > 0 = win, < 0 = loss, pnl == 0 breaks any streak. Returns `{"win": (len, start_date, end_date), "loss": ..., "current": (kind, len)}`.

## Breakdown tables
By pair, by side (buy/sell = Long/Short), by strategy, by weekday. Columns: trades, volume, avg_size, total_pnl, avg_pnl, win_rate, profit_factor (weekday has fewer). PNL columns colored with `pnl_color`.

## Custom SQL
Expander; table name `trades` (filtered data). Errors are shown, not raised.

## Related
- [database.md](database.md): SQL constants, `analytics()`, `streaks()`
- [monthly.md](monthly.md): month-level breakdown (unfiltered); [calendar.md](calendar.md): per-day detail
- [add-trade.md](add-trade.md): manual trades have no `trade_time`, which affects streak order
- [import-csv.md](import-csv.md): source of the data and timezone conversion
- [testing.md](testing.md): `at.main.radio[0]` for the Period filter
