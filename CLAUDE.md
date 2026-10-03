# Trading Journal

Personal, local-only trading journal (single user, no auth). Streamlit web app on `http://localhost:8501`.
SQLite stores trades, DuckDB runs analytics, CSV import supports column mapping. No charts by design (user decision).

## Run
```
./run.sh                 # starts streamlit (extra args pass through, e.g. --server.headless true)
```
Python 3.9 venv in `.venv` (streamlit 1.50, duckdb, pandas). Use `width="stretch"` not `use_container_width` (deprecated).
The sidebar has a "Shut down server" button (SIGTERM to own process). Restart with `./run.sh`; after code edits restart the server.

## Files
| File | Role |
|---|---|
| `app.py` | All UI pages (one `page_*` function each) + sidebar routing at the bottom |
| `db.py` | SQLite schema/CRUD, DuckDB analytics SQL constants, `streaks()` |
| `importer.py` | CSV loader (delimiter/header detection) + `to_trades()` conversion |
| `journal.db` | **Real user data (418 imported trades).** Never delete or overwrite. Copy it before experiments |
| `csv_mappings.json` | Remembered column mappings, keyed by the sorted CSV header signature |
| `docs/` | One doc per feature (below) |

## Feature docs
Each doc ends with a **Related** section linking to the docs that share code or data with it.
- [docs/database.md](docs/database.md) schema, dedupe, DuckDB
- [docs/calendar.md](docs/calendar.md) clickable calendar + day detail
- [docs/monthly.md](docs/monthly.md) monthly view
- [docs/add-trade.md](docs/add-trade.md) manual entry
- [docs/trades.md](docs/trades.md) edit/delete table
- [docs/import-csv.md](docs/import-csv.md) CSV import, MetaTrader, timezone
- [docs/analytics.md](docs/analytics.md) filters, highlights, streaks, breakdowns
- [docs/testing.md](docs/testing.md) how to test without a browser

## Conventions and gotchas
- PNL is stored net of fees in `trades.pnl`. All stats/calendar sum `pnl` directly.
- Colors: green `#26a65b`, red `#e74c3c`, tints `rgba(r,g,b,.2)`. `pnl_color()` in app.py styles DataFrame cells. Side colors: Long blue `#3b82f6`, Short amber `#f59e0b` (`SIDE_COLORS`, `side_color()` for tables, `side_tag()` for HTML); kept distinct from the PNL green/red.
- User's data is a MetaTrader 5 report in broker time GMT+3, journal timezone is GMT+7 (WIB). See import doc.
- `BTCUSD` and `BTCUSD.Daily` are separate pairs (broker symbols). User was offered merging them; not done.
- Pages are called at the bottom of app.py after all defs, so helper order in the file does not matter.
