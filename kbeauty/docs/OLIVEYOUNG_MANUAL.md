# 올리브영 랭킹 — 매주 저장하는 방법

올리브영은 자동 수집이 차단되어 있어서 (이유: `docs/ACCESS_REVIEW.md`)
**매주 1회, 직접 브라우저에서 저장**합니다. 5~10분 걸립니다.

## 언제
매주 **금요일** (요일은 바꿔도 되지만, 매주 같은 요일을 지켜 주세요 —
요일이 바뀌면 주간 비교가 흔들립니다.)

## 순서
1. 아래 주소 6개를 하나씩 브라우저(크롬)에서 엽니다.
2. 페이지가 다 뜨면 `Ctrl + S` → 파일 형식 **"웹페이지, HTML만"** 선택.
3. 저장 위치: `C:\Users\user99i1\buzztrend\kbeauty\data\manual\oliveyoung\`
4. 파일 이름을 **정확히** 아래처럼 (오늘 날짜로):

| 열 주소 | 저장 파일명 (예: 2026-08-07 저장 시) |
|---|---|
| [전체](https://www.oliveyoung.co.kr/store/main/getBestList.do) | `2026-08-07_전체.html` |
| [스킨케어](https://www.oliveyoung.co.kr/store/main/getBestList.do?dispCatNo=900000100100001&fltDispCatNo=10000010001&pageIdx=1&rowsPerPage=100) | `2026-08-07_스킨케어.html` |
| [메이크업](https://www.oliveyoung.co.kr/store/main/getBestList.do?dispCatNo=900000100100001&fltDispCatNo=10000010002&pageIdx=1&rowsPerPage=100) | `2026-08-07_메이크업.html` |
| [마스크팩](https://www.oliveyoung.co.kr/store/main/getBestList.do?dispCatNo=900000100100001&fltDispCatNo=10000010009&pageIdx=1&rowsPerPage=100) | `2026-08-07_마스크팩.html` |
| [선케어](https://www.oliveyoung.co.kr/store/main/getBestList.do?dispCatNo=900000100100001&fltDispCatNo=10000010011&pageIdx=1&rowsPerPage=100) | `2026-08-07_선케어.html` |
| [클렌징](https://www.oliveyoung.co.kr/store/main/getBestList.do?dispCatNo=900000100100001&fltDispCatNo=10000010010&pageIdx=1&rowsPerPage=100) | `2026-08-07_클렌징.html` |

5. 6개 다 저장했으면 아래 명령 실행 (또는 Claude에게 "올리브영 임포트 해줘"):

```bash
cd ~/buzztrend/kbeauty && python cli.py import-oy
```

## 이 명령이 하는 일
- 파일을 읽어 순위·브랜드·상품명·가격·세일 표시를 꺼냅니다
- 상품이 100개가 아니면 **경고**하고, 절반 이하면 **중단**합니다 (저장 실수 방지)
- 원본 파일을 `data/raw/rankings/oliveyoung/` 에 영구 보관합니다 (절대 덮어쓰지 않음)
- 데이터베이스에 넣습니다 — 같은 파일을 두 번 실행해도 중복되지 않습니다

## 주의
- 주 1회 저장이므로 모든 주간 값에는 `low_confidence`(단일 스냅샷) 라벨이 붙습니다.
  이는 오류가 아니라 "한 번 찍은 사진"이라는 표시입니다.
- 빠진 주는 그대로 빈칸(NULL)으로 남습니다. 지난주 것을 저장해서 메꾸지 마세요 —
  날짜가 다르면 데이터가 왜곡됩니다.
- 페이지가 로그인 화면이나 이상한 화면이면 저장하지 말고 알려 주세요.
