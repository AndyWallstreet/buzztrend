# kbeauty tracker — conventions

Data tracker for the Korean cosmetics sector, living inside the buzztrend repo at
`kbeauty/`. It ingests customs exports, Amazon US / 올리브영 rankings, and company
reference data; outputs a monthly Excel report and publishes JSON/aggregates for the
buzztrend Streamlit site. **This module builds no models** — no regressions, no
forecasts, no fitted values. The output must be clean, complete, traceable,
model-ready data.

The user is a beginner — explain things in simple words, Korean preferred for
user-facing text. Never assume they know jargon.

## Decisions already made (2026-07-31)
- Frontend: **new pages in the existing buzztrend Streamlit app** (not a separate
  API service). Phase 5/7 HTTP endpoints from the original spec are adapted to
  Streamlit-native equivalents: shared Python transformation functions instead of
  REST, in-app `st.download_button` for Excel files.
- Location: subfolder `kbeauty/` of the existing `~\buzztrend` repo.
- Data flow: raw caches + DuckDB + Excel archives stay **local only** (gitignored).
  Small published aggregates go to `kbeauty/data/publish/` and are **committed** so
  Streamlit Cloud has them (same pattern as the existing committed `buzztrend.db`).

## Hard rules
- **Never fabricate or interpolate a data point.** Missing stays NULL and gets logged.
- Raw API responses are cached immutably under `data/raw/`; never re-hit for cached
  periods, never overwrite a capture.
- Tidy grain: one row per period × dimension. No pre-aggregation that destroys detail.
- Two time grains, physically separate tables: exports = calendar month (KST),
  rankings = ISO week (`iso_year`, `iso_week`, `week_start_date` = Monday KST).
  Never join on a naive date. Week→month conversion only through `v_ranking_monthly`
  (a week belongs to the month containing its Thursday), rule stated in every footnote.
- Provisional customs (10일/20일 잠정치) live in `fact_export_interim`, never merged
  into confirmed monthlies. Keep vintage + revision history.
- Unmapped HS codes → `unmapped_hs.csv` + warning. Never drop silently.
- Unknown brand origins are flagged for manual review, never guessed.
- Validation gates every build: if reconciliation fails, no artifact is written.
- Excel: data sheets are values-only; derived cells are live Excel formulas; the
  `notes` column belongs to the user and is never overwritten.
- Secrets in `kbeauty/.env` only (see `.env.example`), never committed.

## Environment
- Windows 11, PowerShell. Bare `python` is a broken Store stub — use the real
  interpreter under `%LOCALAPPDATA%\Programs\Python\Python312\python.exe`.
- `make` is not installed. Make targets are implemented as `python cli.py <command>`
  (backfill / refresh / weekly / monthly / report / import-notes / publish / test).
  The Makefile is a thin wrapper kept for documentation.
- Shell clock can lag a day — take "today" from a server source when it matters.
- Storage: DuckDB at `kbeauty/kbeauty.duckdb` (gitignored). Excel via
  openpyxl/xlsxwriter. All timestamps KST.

## Working style
Phase by phase per `PLAN.md`. At the end of each phase: show what was built, what it
was verified against, and open uncertainties — then stop and wait. Prefer reporting a
gap or an unreliable source over quietly picking something plausible.
