"""DuckDB connection and schema for the kbeauty tracker.

Two time grains stay physically separate (see CLAUDE.md):
- exports: calendar month  (Phase 1, tables created there)
- rankings: ISO week, derived from immutable captures
"""
from pathlib import Path

import duckdb

KBEAUTY_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = KBEAUTY_ROOT / "kbeauty.duckdb"

DDL = """
CREATE TABLE IF NOT EXISTS fact_oy_rank_capture (
    capture_date          DATE      NOT NULL,
    category              VARCHAR   NOT NULL,   -- 전체/스킨케어/메이크업/마스크팩/선케어/클렌징
    rank                  INTEGER   NOT NULL,
    goods_no              VARCHAR,
    brand                 VARCHAR,
    product_name          VARCHAR,
    price_original        INTEGER,              -- KRW, NULL when not shown
    price_current         INTEGER,              -- KRW, NULL when not shown
    flags                 VARCHAR,              -- '세일|쿠폰|오늘드림' etc., raw badge text joined
    is_discounted         BOOLEAN,
    rating                DOUBLE,               -- 10-point scale from page, NULL if absent
    product_category_path VARCHAR,              -- e.g. '01 > 스킨케어 > 로션' (site's own tagging)
    source_file           VARCHAR   NOT NULL,
    ingested_at           TIMESTAMP NOT NULL,
    PRIMARY KEY (capture_date, category, rank)
);

-- Weekly record derived from captures. Median is the headline; never interpolated.
-- presence_count counts captures within the ISO week (manual sourcing = usually 1).
-- low_confidence when fewer than 2 captures that week (see spec).
CREATE OR REPLACE VIEW v_oy_weekly AS
WITH captures AS (
    SELECT *,
           isoyear(capture_date)                             AS iso_year,
           weekofyear(capture_date)                          AS iso_week,
           date_trunc('week', capture_date)                  AS week_start_date
    FROM fact_oy_rank_capture
),
week_capture_counts AS (
    SELECT iso_year, iso_week, category,
           COUNT(DISTINCT capture_date) AS captures_in_week
    FROM captures
    GROUP BY 1, 2, 3
)
SELECT
    c.iso_year,
    c.iso_week,
    c.week_start_date,
    c.category,
    c.goods_no,
    any_value(c.brand)                      AS brand,
    any_value(c.product_name)               AS product_name,
    CAST(median(c.rank) AS INTEGER)         AS median_rank,
    MIN(c.rank)                             AS best_rank,
    COUNT(DISTINCT c.capture_date)          AS presence_count,
    any_value(w.captures_in_week)           AS captures_in_week,
    any_value(w.captures_in_week) < 2       AS low_confidence
FROM captures c
JOIN week_capture_counts w
  USING (iso_year, iso_week, category)
GROUP BY c.iso_year, c.iso_week, c.week_start_date, c.category, c.goods_no;
"""


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(DB_PATH))
    con.execute(DDL)
    return con
