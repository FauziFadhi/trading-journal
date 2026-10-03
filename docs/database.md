# Database

`db.py`. SQLite file `journal.db` next to the code; created/migrated automatically by `db.conn()`.

## Table `trades`
| Column | Notes |
|---|---|
| id | autoincrement |
| trade_date | `YYYY-MM-DD`, in the journal timezone (GMT+7) |
| trade_time | `HH:MM:SS` close time, optional (manual trades have none). Used to order trades for streaks |
| symbol | pair/instrument, uppercase for manual entry |
| side | `Long` / `Short` (importer maps buy/sell) |
| qty, entry_price, exit_price, fees | optional numbers, fees default 0 |
| pnl | NOT NULL, net PNL |
| strategy, notes | free text |
| status | `closed` (default, all imported/existing rows) or `open`. Open trades are excluded by `load_trades()` so they never affect PNL, calendar, analytics or the import overlap check |
| opened_at | `YYYY-MM-DD HH:MM:SS`, set only for trades added as open (and kept after closing) |
| row_hash | UNIQUE sha1 of all `COLUMNS` values, so `INSERT OR IGNORE` skips exact duplicates |

`conn()` also migrates older DBs (`ALTER TABLE ADD COLUMN` for `trade_time`, `status`, `opened_at`). `COLUMNS` is deliberately unchanged by `status`/`opened_at` because it feeds `row_hash`; changing it would break duplicate detection for already-saved rows. `COLUMNS` in db.py is the single list of editable columns; insert/update/hash all use it. Adding a column means: SCHEMA, migration in `conn()`, `COLUMNS`, `update_trades` SQL.

## Functions
- `prepare(row)` cleans NaN to None and adds `row_hash` (used by `insert_trades` and the importer overlap check).
- `insert_trades(rows)` returns `(inserted, skipped_duplicates)`.
- `load_open_trades()`, `insert_open_trade(...)`, `close_trade(id, date, time, exit, fees, pnl)` handle running trades. `pnl` is a 0 placeholder while open (column is NOT NULL); `row_hash` is NULL until closed (UNIQUE allows many NULLs).
- `load_trades()` returns closed trades only (no `status` column), a DataFrame ordered by date, time, id descending.
- `update_trades(df)` updates by `id`; `delete_trades(ids)`.
- `calc_pnl(side, qty, entry, exit, fees)`: `(exit-entry)*qty*dir - fees`, dir = -1 for Short. Returns None if prices missing.
- `analytics(sql, df)`: registers the DataFrame as table `trades` in an in-memory DuckDB and returns a DataFrame. DuckDB never touches the SQLite file (no sqlite extension needed), so all analytics respect whatever filtered DataFrame is passed.
- SQL constants: `SUMMARY_SQL`, `BY_STRATEGY_SQL`, `BY_SYMBOL_SQL`, `BY_SIDE_SQL`, `BY_WEEKDAY_SQL`, `BY_MONTH_SQL`, `DAILY_SQL`, `BEST_DAY_SQL` (has `{order}` placeholder).
- `streaks(df)`: see analytics doc.

## Gotchas
- Re-importing the same trades with a different timezone changes `trade_date/time`, so the hash differs; the import page flags these as "probable duplicates" and can replace them.
- Editing a row in the Trades page changes its data but not its stored `row_hash`.

## Related
- [import-csv.md](import-csv.md): writes rows via `insert_trades`, timezone/duplicate caveats
- [add-trade.md](add-trade.md) and [trades.md](trades.md): the other writers (manual entry, edit/delete)
- [analytics.md](analytics.md), [monthly.md](monthly.md): the DuckDB SQL constants and `streaks()` live in db.py
- [calendar.md](calendar.md): reads trades with `load_trades()`
- [testing.md](testing.md): do not write to the real `journal.db` in tests
