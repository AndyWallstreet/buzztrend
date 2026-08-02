# K-Beauty Tracker — 단계별 계획 (PLAN)

한국 화장품 섹터 데이터 트래커. 수출(관세청) · Amazon US 랭킹 · 올리브영 랭킹 ·
기업 참고자료를 정해진 주기로 수집해서, **월간 엑셀 리포트**와 buzztrend 사이트용
데이터를 만듭니다.

> 이 프로젝트는 **모델을 만들지 않습니다.** 예측·회귀 없음. 깨끗하고, 빠짐없이,
> 출처를 추적할 수 있는 "모델에 바로 넣을 수 있는" 데이터가 목표입니다.
> 빠진 데이터는 채우지 않고 NULL로 두고 기록만 남깁니다.

## 확정된 결정 (2026-07-31)
| 항목 | 결정 |
|---|---|
| 프론트엔드 | 기존 buzztrend Streamlit 앱에 **새 페이지 추가** (하츄핑 페이지와 같은 방식) |
| 위치 | 기존 `~\buzztrend` 저장소 안의 `kbeauty/` 하위 폴더 |
| 실행 방식 | 윈도우에 `make`가 없어서 `python cli.py <명령>`으로 실행 (Makefile은 참고용) |
| 데이터 보관 | 원본 캐시·DuckDB·엑셀 보관본은 **내 컴퓨터에만** (git 제외). 사이트용으로 정리된 작은 JSON만 `data/publish/`에 커밋 → Streamlit Cloud가 사용 (기존 buzztrend.db 커밋 방식과 동일) |

### 원래 스펙에서 조정된 부분 (Streamlit 선택에 따라)
- Phase 5의 `/api/...` REST 엔드포인트 → Streamlit은 API 서버가 아니므로, **같은
  파이썬 변환 함수를 사이트 페이지가 직접 불러 쓰는 방식**으로 대체합니다.
  "지표를 프론트에서 다시 구현하지 않는다"는 원칙은 그대로 지켜집니다.
- Phase 7의 다운로드 엔드포인트 → Streamlit의 다운로드 버튼(`st.download_button`)
  으로 대체. 파일 목록·버전·해시 검증·"검증 실패한 파일은 절대 제공 안 함" 규칙은
  그대로 유지합니다.
- Phase 7C 비동기 커스텀 엑셀 생성 → Streamlit Cloud에는 백그라운드 작업 큐가
  없으므로, 페이지 안에서 동기 생성 + 행 수 상한(초과 시 명확한 에러)으로 조정.

---

## Phase 0 — 뼈대 만들기 ✅ (지금 단계)
- [x] 폴더 구조, `CLAUDE.md`(작업 규칙), `PLAN.md`(이 문서)
- [x] `.env.example` (`CUSTOMS_API_KEY`, `DART_API_KEY`), `requirements.txt`, Makefile
- [x] 루트 `.gitignore`에 kbeauty 대용량 파일 제외 규칙 추가
- [ ] **사용자 승인 대기 ← 여기서 멈춤. ETL 코드는 아직 없음**

> **진행 상황 (2026-07-31):** Phase 1은 data.go.kr 시스템 점검(~8/2 18:00)으로
> API 키 신청이 막혀 대기 중. **단, 사전 확인은 완료**: 무역통계 포털에서 월간 ×
> 국가 × HS 10자리 데이터 존재를 눈으로 검증했고, 카테고리 맵의 초기 가정 두 개를
> 수정함 (선케어 분리 불가, 마스크팩은 3307904000) — `docs/HSK_FINDINGS.md`.
> Phase 2는 접근성 검토 완료(`docs/ACCESS_REVIEW.md`) — Amazon은 **보류**(사용자
> 결정), 올리브영은 **주 1회 수동 저장** 방식으로 파서·DB·테스트까지 구축 완료
> (`docs/OLIVEYOUNG_MANUAL.md`). DART 키는 점검과 무관하게 지금 신청 가능.

## Phase 1 — 관세청 수출 데이터 (월간)
1. API를 한 번 호출해 원본 응답을 `data/raw/sample.json`으로 저장하고, **실제 필드
   이름과 세부 수준(10자리 HSK 가능 여부)을 먼저 보여드림.** 스키마를 추측하지 않음
2. 2015-01부터 백필. 원본 응답은 `data/raw/customs/{yyyymm}.json`에 캐시, 캐시된
   기간은 다시 호출하지 않음. 호출 간격 제한 + 재시도(backoff)
3. DuckDB 적재: (기간, HS코드, 국가, vintage) 기준 멱등 upsert. USD·중량(kg)·수량 저장
4. 10일/20일 잠정치는 **별도 테이블** `fact_export_interim` + 수정 이력 테이블
5. 카테고리 매핑 `config/hs_category_map.yaml` — 스펙의 초기 추측(색조 3304.10/20/30/91,
   기초 3304.99, 향수 3303, 두발 3305, 구강 3306, 인체세정 3401.30, 면도·데오 3307)을
   **API가 주는 실제 HSK 목록과 대조해 검증·수정**
6. 3304.99(기초+마스크팩+선케어 혼합)는 10자리에서 최대한 분리, 분리 불가능한 부분은
   `docs/DATA_CAVEATS.md`에 명시
7. 매핑 안 된 HS코드 → `unmapped_hs.csv` + 경고. 조용히 버리지 않음
8. 지역 구분: 중국/홍콩(분리, 합산 토글 제공)/미국/일본/베트남·동남아/EU/러시아·CIS/
   중동/중남미/기타
9. 검증: 품목별 합계 ↔ 국가별 총액 API 상호 대조(reconciliation)

## Phase 2 — 랭킹 수집 (주간)
**수집기 코드를 짜기 전에** 두 소스 모두 접근성 검토부터:
- robots.txt 확인 결과 보고 + 선택지(비용·안정성 비교) 제시 → **사용자가 선택**
- Amazon: 정식 경로는 Product Advertising API 또는 유료 서비스(Keepa, Rainforest,
  DataForSEO). 직접 스크래핑을 기본값으로 하지 않음
- 올리브영이 자동 수집을 막으면 → 보고하고 중단 (수동 소싱으로 전환)

수집 설계 (소스 확정 후):
- 주 3회(월/수/금, KST 고정 시각) 캡처, `data/raw/rankings/{source}/{날짜}.json`에
  불변 저장. 주간 값 = **중앙값 랭크 + 최고 랭크 + 캡처 횟수(3 중 몇 회)**
- 주간 캡처 2회 미만 → `low_confidence` 라벨. **빠진 랭킹은 절대 보간하지 않음**
- Amazon: 전체 Top 100 + Skin Care/Makeup/Sunscreen/Lip/Face Masks. 브랜드 국적은
  `config/brand_registry.yaml`, 모르는 브랜드는 추측하지 않고 검토 목록으로
- 올리브영: 전체 Top 100 + 스킨케어/메이크업/마스크팩/선케어/클렌징. 올영세일 주간
  플래그 + 세일 주 제외 토글(기본 켜짐)
- 시간 단위: 수출=월, 랭킹=ISO주 — 물리적으로 분리. 주→월 변환은 `v_ranking_monthly`
  뷰 하나로만 (목요일이 속한 달 규칙), 5주 달 왜곡을 잡는 단위 테스트 포함

## Phase 3 — 기업 참고 데이터 (월간)
- OpenDART: 분기 매출·영업이익, 사업부문별·지역별 매출, 수출/내수
- `config/entity_map.yaml`: 연결 자회사, 국가, 현지생산 여부 (해석용 참고자료 —
  분석은 하지 않음)
- pykrx: 일별 종가, 시가총액, 상장주식수
- `docs/DATA_CAVEATS.md` 필수 작성: **관세청 데이터는 "누가 만들었나"가 아니라
  "한국에서 어떤 HS코드로 나갔나"의 기록** — ODM 주의사항, 해외 자회사 생산은
  관세청에 안 잡힘, 실리콘투만 예외(직접 수출자). UI와 엑셀에도 표시

## Phase 4 — 엑셀 리포트 (핵심 산출물)
- 파일명 `output/buzztrend_kbeauty_2026-07_w31.xlsx`, 모든 버전 보존
- 주간 갱신: `05_Amazon`, `06_OliveYoung`, `08_Data_Quality`, `CHANGELOG`만 수정
- 월간 갱신: 전체 재생성
- 시트: 00_Summary(수출 기준월·랭킹 기준주 **별도 표기**) / 01_Export_Monthly /
  02_Country_Matrix / 03_Category_Matrix / 04_Interim / 05_Amazon / 06_OliveYoung /
  07_Companies / 08_Data_Quality / 99_Sources / CHANGELOG
- 데이터 시트는 값만, 파생 계산은 **살아있는 엑셀 수식**. 이름 정의된 범위, 틀 고정,
  자동 필터. USD 천 단위, % 소수 1자리, 음수 빨간 괄호. 한/영 병기 헤더
- `notes` 열은 사용자 전용 — 파이프라인이 절대 덮어쓰지 않음
- 갱신 후에도 수식·차트·이름 범위·메모가 살아있는지 명시적 테스트
  (월간 생성 → 주간 4회 → 다음 달 월간 → 전부 생존 확인)

## Phase 5 — buzztrend 사이트 페이지
- 같은 DB, 같은 변환 코드 — 지표를 프론트에서 다시 구현하지 않음
- 페이지: 개요 / 국가별 / 카테고리별 / Amazon / 올리브영 / 기업 / 데이터 품질
- 한국어 우선, 영어 병기. **수출(월간, YYYY-MM)과 랭킹(주간, YYYY-Www) 최신성 배지를
  따로따로 표시** — 하나의 "마지막 업데이트"로 합치지 않음
- 사이트용 데이터는 `data/publish/`의 커밋된 파일에서 읽음

## Phase 6 — 자동화 (윈도우 작업 스케줄러)
- 주간: 월요일 09:00 KST — 직전 완료된 ISO 주 처리
- 월간: 매월 16일 (관세청 확정치 이후). 잠정치는 11일·21일에 `04_Interim`만 갱신
- **트랙별 독립 검증**: 랭킹 실패가 월간 수출 리포트를 막지 않음 (반대도 동일)
- 검증 실패 시 산출물을 쓰지 않음 — 틀린 리포트보다 없는 리포트가 낫다
- 실행 리포트: `logs/weekly_YYYY-Www.md`, `logs/run_YYYYMM.md`

## Phase 7 — 엑셀 다운로드 & 커스텀 내보내기
- 7A 파일 등록부 `dim_report_file`: 파일명, 기간, sha256, 데이터 vintage, is_latest
- 7B 다운로드: Streamlit 다운로드 페이지(버전 목록 + vintage 표시 + "최신" 버튼).
  제공 전 sha256 검증, 검증 실패한 빌드 파일은 절대 제공하지 않음
- 7C 커스텀 내보내기: 현재 필터로 엑셀 생성. **Filters 시트가 맨 앞** (선택한 필터
  + 데이터 vintage 기록). 30일 후 만료, 행 수 상한
- 7D 메모 왕복: `python cli.py import-notes FILE=...` — notes 열을 자연 키
  (기간, HS코드, 국가)로 `user_notes` 테이블에 저장, 다음 빌드 때 재주입. 키가
  사라진 메모는 삭제하지 않고 orphan으로 보관·보고. **7D를 먼저 증명한 뒤에**
  (두 달 사이클 시연) 나머지 Phase 7을 그 위에 얹음
- 7E 공개는 수동: 빌드가 파일을 만들어도, 사이트 공개는 별도 명령
  (`python cli.py publish FILE=...`) — 보고 나서 올림

---

## 실행 명령 (make 대신)
```
python cli.py backfill      # 과거 데이터 채우기
python cli.py refresh       # 최신 데이터 갱신
python cli.py weekly        # 주간 랭킹 갱신 (WEEK=2026-W31)
python cli.py monthly       # 월간 전체 빌드 (MONTH=2026-07)
python cli.py report        # 엑셀 생성
python cli.py import-notes  # 엑셀 메모 다시 읽기
python cli.py publish       # 사이트에 공개
python cli.py test          # 테스트 실행
```

## 진행 방식
한 Phase가 끝날 때마다: 만든 것 / 무엇으로 검증했는지 / 불확실한 점을 보여드리고
**멈춰서 승인을 기다립니다.** 애매한 HS 매핑, 모르는 브랜드 국적, 접근 제한 소스는
추측하지 않고 보고합니다.
