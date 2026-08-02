# 랭킹 소스 접근성 검토 (Phase 2 사전 조사)

조사일: 2026-07-31

## Amazon US

**robots.txt** (www.amazon.com/robots.txt, 2026-07-31 확인):
- 베스트셀러 경로(`/gp/bestsellers`, `/Best-Sellers`)를 막는 규칙 **없음**
- 차단 대상은 로그인·장바구니·리뷰 작성·위시리스트 등 개인화 경로
- 단, robots.txt와 별개로 Amazon 이용약관(Conditions of Use)은 자동 수집을
  금지하며, 실제로 봇 차단이 강력함 → 직접 스크래핑은 약관 위반 + 유지보수 부담

**정식 경로 비교** (2026-07 웹 조사 기준, 결제 전 최신 가격 재확인 필요):

| 경로 | 비용 | 베스트셀러 지원 | 비고 |
|---|---|---|---|
| Keepa API | €49/월~ (토큰제) | ✅ 전용 Best Sellers 엔드포인트 | 판매랭크 이력·리뷰 수까지. 파이썬 클라이언트 있음 |
| Rainforest API | $66/월~ (10,000 크레딧) | ✅ 전용 bestsellers 타입 | 파싱된 top100 반환. 우리 사용량(월 ~160건)엔 과한 티어 |
| DataForSEO | 종량제 $0.0006~/건 | ❌ **없음** (키워드 검색·ASIN 조회만) | 공식 문서 확인 결과 베스트셀러 목록 미지원 → 탈락 |
| PA-API (공식, 무료) | 무료 | 부분적 | Amazon Associates 가입 + 180일 내 판매 3건 필요, 유지에 월 ~10건 판매 — 어필리에이트 사이트 없으면 사실상 불가 → 탈락 |

우리 사용량 추정: 6개 리스트(전체+5 카테고리) × 주 3회 = 주 18회, 월 ~80회 수집.
어느 유료 플랜이든 최저 티어로 충분함.

## 올리브영 (oliveyoung.co.kr)

**robots.txt** (2026-07-31, 실제 브라우저로 확인):
- Googlebot, Yeti(네이버), ClaudeBot, GPTBot 등 **이름이 명시된 크롤러만**
  일부 경로 허용 (`/store/main/getBestList.do` 등)
- **그 외 모든 클라이언트(`User-agent: *`)는 전체 차단(`Disallow: /`)**
  → 우리가 만들 수집기는 여기에 해당
- 추가로 Cloudflare 봇 차단(managed challenge)이 스크립트 HTTP 요청을
  robots.txt 수준에서부터 차단함 (PowerShell 요청이 챌린지 페이지를 받음)

**결론: 올리브영은 자동 수집이 차단되어 있음.** 차단 우회는 하지 않는다는
원칙(스펙 + 안전 규칙)에 따라 자동 수집기는 만들지 않고, 수동 소싱으로 전환.
→ 사용자가 주기적으로 랭킹 페이지를 저장하면 파서가 `data/manual/oliveyoung/`
에서 읽어 들이는 구조로 설계.

수동 소싱 시 주의: 주 1회 저장이면 캡처 1회짜리 주간값 — 스펙의 노이즈 경고에
따라 모든 화면·엑셀에서 "단일 스냅샷" 라벨을 붙이고 DATA_CAVEATS.md에 기록.

## 출처
- https://frontdeskreview.com/software/amazon-seller-tools/keepa/
- https://revenuegeeks.com/software/keepa/pricing
- https://flybyapis.com/blog/rainforest-api-alternatives/
- https://www.asinspotlight.com/blog/asinspotlight-api-vs-rainforest-api
- https://costbench.com/software/seo-tools/dataforseo/
- https://docs.dataforseo.com/v3/merchant/amazon/overview/
- https://affiliate-program.amazon.com/help/node/topic/GVJ2BJP35457CLML
- https://www.keywordrush.com/blog/amazon-pa-api-associatenoteligible-error-is-there-a-new-10-sales-rule/
