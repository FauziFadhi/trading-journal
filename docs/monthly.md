# Monthly (page "Monthly")

`page_monthly`. Data from `db.BY_MONTH_SQL` (DuckDB), all trades, no filters.

- Year select (years present in data, newest first).
- Metrics for that year: PNL, trades, profitable months (`x / months with trades`).
- 12 cards Jan to Dec (CSS grid `.mgrid`/`.mc`): PNL, trades, win rate, volume. Green/red tint; months without trades are greyed.
- Table "All months" (all years, newest first): trades, trading days, volume, avg size, total/avg PNL, win rate, profit factor, running `cumulative` PNL (computed in pandas over ascending months, then reversed for display). PNL columns use `pnl_color`.

Not yet: pair/side filters, clicking a month card to open the Calendar on it.

## Related
- [calendar.md](calendar.md): day-by-day view of a month
- [analytics.md](analytics.md): same metrics with pair/side/week/date filters; `pnl_color` is shared
- [database.md](database.md): `BY_MONTH_SQL`
- [import-csv.md](import-csv.md): timezone conversion affects which month late-evening trades land in
