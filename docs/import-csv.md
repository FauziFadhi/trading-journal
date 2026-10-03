# Import CSV (page "Import CSV")

`page_import` (app.py) + `importer.py`.

## Flow
1. Upload CSV. `importer.load_csv(bytes)`:
   - decodes utf-8-sig (fallback latin-1);
   - delimiter = the one of `, ; \t |` with most occurrences;
   - header row = first of the first 50 rows with >= 3 fields and >= 70% non-empty (skips preamble such as MetaTrader's account lines);
   - duplicate header names become `Price`, `Price.1`;
   - stops at the first blank line (so later sections like Open Trades are ignored); rows whose first two cells are empty (footers like "Closed P/L") are skipped.
2. Preview + column mapping selectboxes for each journal field. Defaults: remembered mapping for this exact header set (`csv_mappings.json`), else `guess()` using `ALIASES` in app.py (add aliases there). Date and Symbol required; PNL, or qty+entry+exit to compute it.
3. Options: day-first dates, "PNL column is gross: subtract fees" (`pnl - abs(fees)`), default strategy, **CSV timezone** (default GMT+3) and **Journal timezone** (default GMT+7).
4. `importer.to_trades()` returns `(clean_df, bad_mask, dropped_count)`: normalizes side (buy/long -> Long, sell/short -> Short), drops non-trade types (balance, credit, deposit, withdrawal, correction, bonus, charge, rebate, commission), parses numbers (`$`, commas, `(1.50)` negatives), parses datetime into `trade_date` + `trade_time` (time kept only if the column has any time component), shifts by `dst_tz - src_tz` hours, computes missing PNL.
5. **Overlap check** (shown before the Import button): `importer.classify(good_rows, existing)` labels each row `new`, `exact` (same `row_hash` as a saved trade, always skipped) or `probable` (same symbol/side/qty/entry/exit/PNL ignoring date and time, usually the same trade imported with another timezone). Shows the file vs journal date range, counts, and an expander listing every overlapping row next to the saved trade (`saved_id`, saved date/time). For probable duplicates choose **skip** (default), **import anyway**, or **replace saved trades** (deletes the matching saved rows, imports the file's version, the way to fix a timezone mistake).
6. `db.insert_trades` skips exact duplicates; mapping is saved; message reports imported/duplicates/invalid/non-trade counts.

## MetaTrader 5 report (user's file)
Semicolon CSV, "Order History" preamble. Mapping used: Close Time -> date, Item -> symbol, Type -> side, Volume -> qty, Price -> entry, Price.1 -> exit, Commission -> fees, Profit -> pnl. 418 trades, total 311.87 = report's "Closed P/L". Times are broker GMT+3, converted to GMT+7 (68 trades moved to the next calendar day). Commission/taxes/swap were all 0; swap is never subtracted. Profit is gross of commission, so tick "subtract fees" if commission is nonzero.

## Gotchas
- Re-import with different timezone no longer silently duplicates: those rows show as "probable duplicates"; use the replace option. Matching is by trade values, so two genuinely distinct trades with identical pair/side/size/prices/PNL are treated as one probable match.
- Open positions section of MT reports is intentionally ignored.

## Related
- [database.md](database.md): `insert_trades`, dedupe via `row_hash`, schema
- [trades.md](trades.md): delete rows before a timezone re-import
- [calendar.md](calendar.md), [monthly.md](monthly.md), [analytics.md](analytics.md): all grouping depends on the converted `trade_date`/`trade_time`
- [testing.md](testing.md): test the importer directly (AppTest cannot upload files)
