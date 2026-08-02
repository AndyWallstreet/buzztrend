# HSK granularity check — tradedata.go.kr, verified by eye (2026-07-31)

Phase 1 pre-check required by the spec: "browse first, confirm HSK granularity by
eye, correct my starting guess." Done on the 수출입 실적 query screen
(품목별+국가별 mode) before writing any loader.

## What the portal/database provides
- Grain confirmed: **month × country × HS 10-digit**, monthly selectable from 2000.
- Values: weight (ton/kg) + USD amount, export and import separately.
- Query modes: 품목별 / 품목별+국가별 / 국가별 / 대륙별 / 경제권별 / 세관별 등.
- Export buttons on results: xlsx / json / csv.
- Verified live: query for 3304991000, 2026-05, by country returned rows
  (e.g. 2026.05 | 가나 | 3304991000 | 기초화장용 제품류 | 0.5 ton | $24k).

## Corrections to the starting category map (important)

1. **3304.99 splits into only two 10-digit codes:**
   - `3304991000` 기초화장용 제품류 (Skin care cosmetics)
   - `3304999000` 기타 (Other)
   There is no finer split.

2. **선케어 (sunscreen) has NO dedicated HSK code.** Sunscreen is included in the
   3304 heading text ("선스크린과 선탠 제품류를 포함한다") but gets no own
   subdivision — it is buried in 3304991000/3304999000 and **cannot be separated**
   in customs data. → must be stated in DATA_CAVEATS and shown in UI/Excel.

3. **마스크팩 has its own code — under 3307, not 3304.99:**
   - `3307904000` 마스크 팩 (Mask pack)
   The starting guess assumed mask packs were mixed inside 3304.99. In the current
   HSK they are separable via 3307.90. Consequence: the 3307 heading is NOT purely
   면도/데오 — the category map must carve 3307904000 out as 마스크팩.
   - **To verify during backfill:** this code was likely introduced in a past HSK
     revision (~2017). Before that, mask packs sat elsewhere (probably 3304.99).
     The backfill must check code validity windows per year and document the break
     in series. Do not assume the code exists back to 2015.

4. Other 10-digit codes sighted (색조 lines have 10-digit children):
   `3304109000`(립 기타), `3304209000`(아이 기타), `3304309000`(네일 기타),
   `3304919000`(파우더 기타), `3305909000`, `3307109000`, `3307490000`,
   `3307909000`. Full child lists to be enumerated from the API's HSK list in
   Phase 1 proper.

## Implication for the pipeline
The data exists at the grain the tracker needs. The portal is interactive
(JS-driven, session-based) — fine for eyeballing, wrong tool for a monthly
automated backfill. The OpenAPI (data.go.kr 15100475) remains the ingestion path;
key application possible after the data.go.kr maintenance ends 2026-08-02 18:00.
