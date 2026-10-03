# Testing without a browser

Use Streamlit's `AppTest` (run from project root with `.venv/bin/python`):
```python
from streamlit.testing.v1 import AppTest
at = AppTest.from_file("app.py", default_timeout=60); at.run()
at.sidebar.radio[0].set_value("Analytics").run()      # page navigation (sidebar radio)
at.main.radio[0].set_value("Week").run()              # page widgets live under at.main
[b for b in at.main.button if b.key == "day_2026-06-18"][0].click().run()
assert not at.exception
```
- Use `at.main.*` for page widgets; `at.radio[i]` ordering mixes sidebar and main and caused errors.
- Clicking "Yes, stop" in the sidebar SIGTERMs the test process itself.
- File upload is not supported by AppTest; test `importer.load_csv` / `to_trades` directly with the CSV bytes.
- AppTest uses the real `journal.db`. Do not write to it in tests; copy `journal.db` aside first if you must.
- `accept_new_options` selectboxes (the Symbol field) cannot be given a new value in AppTest; only existing options can be set. Test new-symbol typing manually.
- AppTest only proves logic and rendering; colors/layout were never visually checked in a browser.

## Related
- [database.md](database.md): protect `journal.db`
- [import-csv.md](import-csv.md): `load_csv` / `to_trades` for upload-free tests
- [calendar.md](calendar.md): day button keys `day_YYYY-MM-DD`
- [analytics.md](analytics.md): filter widget layout
