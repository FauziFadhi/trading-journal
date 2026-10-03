# Calendar (page "Calendar")

`page_calendar` in app.py. Default page.

- Year number input + month select (defaults to today).
- If open trades exist, an info banner says they are not counted.
- Metrics: month PNL, trades, win rate, trading days.
- Mon to Sun grid, 8th column is the weekly total (colored box, only counts days inside the month).
- **Each day is a `st.button`** with key `day_YYYY-MM-DD` and label `day  \n**pnl**  \ntrades` (markdown line breaks). Days with trades are tinted green/red; other-month cells are empty.
- Colors and the selected-day outline (blue) are injected as one `<style>` block using the `.st-key-day_<date> button` classes Streamlit adds from widget keys. Base button style targets `[class*='st-key-day_']`.
- Clicking stores `st.session_state.sel_day` and reruns. Changing month/year clears the selection.
- Day detail under the grid: heading with colored total, trade count and total volume, and a table of that day's trades with colored `pnl` column. Days without trades show "no trades".
- Uses pandas `dt.date` column `d` on a copy of trades (dropped before display along with `row_hash`).

## Related
- [monthly.md](monthly.md): year-level view of the same monthly totals
- [analytics.md](analytics.md): week/date-range filtering and streaks across the same trades
- [trades.md](trades.md): edit or delete a trade you see in the day detail
- [database.md](database.md): `trade_date`/`trade_time` and why dates are in GMT+7
- [import-csv.md](import-csv.md): why some trades fall on a different day (timezone conversion)
