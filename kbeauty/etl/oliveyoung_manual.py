"""올리브영 수동 저장 파일 파서 & 임포터.

올리브영은 자동 수집이 차단되어 있으므로 (robots.txt 전체 차단 + Cloudflare,
docs/ACCESS_REVIEW.md 참고) 사용자가 브라우저에서 직접 저장한 랭킹 페이지를
읽어 들인다. 절대 사이트에 자동 접속하지 않는다.

입력: data/manual/oliveyoung/YYYY-MM-DD_카테고리.html  (Ctrl+S로 저장한 파일)
처리: 파싱 → 검증 → data/raw/rankings/oliveyoung/ 에 불변 보관 → DuckDB 적재
"""
from __future__ import annotations

import hashlib
import re
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime, date
from pathlib import Path

from bs4 import BeautifulSoup

from .db import connect, KBEAUTY_ROOT

MANUAL_DIR = KBEAUTY_ROOT / "data" / "manual" / "oliveyoung"
RAW_DIR = KBEAUTY_ROOT / "data" / "raw" / "rankings" / "oliveyoung"
LOG_DIR = KBEAUTY_ROOT / "logs"

VALID_CATEGORIES = {"전체", "스킨케어", "메이크업", "마스크팩", "선케어", "클렌징"}
FILENAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(.+)\.html?$")

# 100위 목록이 기본. 이보다 적으면 저장이 잘못됐을 가능성이 높아 경고한다.
EXPECTED_COUNT = 100
MIN_ACCEPTABLE = 95


@dataclass
class RankRow:
    capture_date: date
    category: str
    rank: int
    goods_no: str | None
    brand: str | None
    product_name: str | None
    price_original: int | None
    price_current: int | None
    flags: str | None
    is_discounted: bool
    rating: float | None
    product_category_path: str | None
    source_file: str


class ParseError(Exception):
    pass


def _to_int(text: str | None) -> int | None:
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


def parse_file(path: Path, capture_date: date, category: str) -> list[RankRow]:
    """저장된 랭킹 페이지 HTML 하나를 RankRow 목록으로 파싱한다."""
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "lxml")
    cards = soup.select("div.prd_info")
    if not cards:
        raise ParseError(
            f"{path.name}: 상품 카드(div.prd_info)를 찾지 못했습니다. "
            "페이지 구조가 바뀌었거나 저장이 잘못된 파일입니다."
        )

    rows: list[RankRow] = []
    for i, card in enumerate(cards):
        rank_el = card.select_one("span.thumb_flag")
        rank = _to_int(rank_el.get_text()) if rank_el else None
        if rank is None:
            rank = i + 1  # 순번 배지가 없으면 문서 순서를 사용 (경고는 검증 단계에서)

        thumb = card.select_one("a.prd_thumb")
        goods_no = thumb.get("data-ref-goodsno") if thumb else None

        brand_el = card.select_one("span.tx_brand")
        name_el = card.select_one("p.tx_name")

        org_el = card.select_one("p.prd_price span.tx_org span.tx_num")
        cur_el = card.select_one("p.prd_price span.tx_cur span.tx_num")
        price_original = _to_int(org_el.get_text()) if org_el else None
        price_current = _to_int(cur_el.get_text()) if cur_el else None
        # 세일이 없는 상품은 가격이 하나만 표시된다 → 그 값이 현재가
        if price_current is None and price_original is not None:
            price_current, price_original = price_original, None

        flag_els = card.select("p.prd_flag span.icon_flag")
        flags = "|".join(f.get_text(strip=True) for f in flag_els) or None
        is_discounted = bool(
            (price_original is not None and price_current is not None
             and price_current < price_original)
            or (flags and ("세일" in flags or "쿠폰" in flags))
        )

        rating = None
        point_el = card.select_one("p.prd_point_area .point")
        if point_el:
            m = re.search(r"([\d.]+)\s*점\s*$", point_el.get_text(strip=True))
            if m:
                rating = float(m.group(1))

        cat_btn = card.select_one("button[data-ref-goodscategory]")
        cat_path = cat_btn.get("data-ref-goodscategory") if cat_btn else None

        rows.append(RankRow(
            capture_date=capture_date,
            category=category,
            rank=rank,
            goods_no=goods_no,
            brand=brand_el.get_text(strip=True) if brand_el else None,
            product_name=name_el.get_text(strip=True) if name_el else None,
            price_original=price_original,
            price_current=price_current,
            flags=flags,
            is_discounted=is_discounted,
            rating=rating,
            product_category_path=cat_path,
            source_file=path.name,
        ))
    return rows


def validate(rows: list[RankRow], warnings: list[str]) -> None:
    """행 수·랭크 연속성 검증. 문제는 warnings에 쌓고, 치명적이면 예외."""
    n = len(rows)
    if n < MIN_ACCEPTABLE:
        raise ParseError(
            f"상품이 {n}개만 파싱되었습니다 (기대: {EXPECTED_COUNT}). "
            "페이지를 끝까지 연 뒤 저장했는지 확인해 주세요."
        )
    if n != EXPECTED_COUNT:
        warnings.append(f"상품 수가 {n}개입니다 (기대 {EXPECTED_COUNT}) — 그대로 적재하되 기록해 둡니다.")
    ranks = [r.rank for r in rows]
    if len(set(ranks)) != len(ranks):
        raise ParseError("랭크 번호에 중복이 있습니다. 저장 파일을 확인해 주세요.")
    expected = list(range(1, n + 1))
    if sorted(ranks) != expected:
        warnings.append("랭크 번호가 1..N 연속이 아닙니다 — 페이지 구조 변화 가능성, 확인 필요.")
    null_brands = sum(1 for r in rows if not r.brand)
    if null_brands:
        warnings.append(f"브랜드가 비어 있는 상품 {null_brands}개 (NULL로 적재).")


def _archive(path: Path) -> Path:
    """원본 파일을 불변 보관소로 복사. 같은 이름의 다른 내용이 있으면 중단."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    dest = RAW_DIR / path.name
    if dest.exists():
        if hashlib.sha256(dest.read_bytes()).hexdigest() == hashlib.sha256(path.read_bytes()).hexdigest():
            return dest  # 동일 파일 재실행 → 그대로 진행 (멱등)
        raise ParseError(
            f"보관소에 같은 이름의 다른 파일이 이미 있습니다: {dest.name}. "
            "기존 캡처는 덮어쓰지 않습니다. 파일명을 확인해 주세요."
        )
    shutil.copy2(path, dest)
    return dest


def import_file(path: Path) -> tuple[int, list[str]]:
    """수동 저장 파일 하나를 검증·보관·적재. (적재 행 수, 경고 목록) 반환."""
    m = FILENAME_RE.match(path.name)
    if not m:
        raise ParseError(
            f"파일명 형식이 맞지 않습니다: {path.name} "
            "(예: 2026-07-31_스킨케어.html)"
        )
    capture_date = date.fromisoformat(m.group(1))
    category = m.group(2)
    if category not in VALID_CATEGORIES:
        raise ParseError(
            f"알 수 없는 카테고리 '{category}'. 사용 가능: {', '.join(sorted(VALID_CATEGORIES))}"
        )

    warnings: list[str] = []
    rows = parse_file(path, capture_date, category)
    validate(rows, warnings)
    _archive(path)

    con = connect()
    try:
        con.execute("BEGIN")
        # 같은 (날짜, 카테고리) 재실행 시 교체 → 멱등
        con.execute(
            "DELETE FROM fact_oy_rank_capture WHERE capture_date = ? AND category = ?",
            [capture_date, category],
        )
        now = datetime.now()
        con.executemany(
            """INSERT INTO fact_oy_rank_capture VALUES
               (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                [r.capture_date, r.category, r.rank, r.goods_no, r.brand,
                 r.product_name, r.price_original, r.price_current, r.flags,
                 r.is_discounted, r.rating, r.product_category_path,
                 r.source_file, now]
                for r in rows
            ],
        )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()
    return len(rows), warnings


def import_all() -> int:
    """data/manual/oliveyoung/ 의 모든 파일을 적재. 실행 리포트를 남긴다."""
    MANUAL_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in MANUAL_DIR.glob("*.htm*") if FILENAME_RE.match(p.name))
    skipped = [p.name for p in MANUAL_DIR.glob("*.htm*") if not FILENAME_RE.match(p.name)]

    report_lines = [f"# 올리브영 수동 임포트 {datetime.now():%Y-%m-%d %H:%M}", ""]
    ok = fail = 0
    for f in files:
        try:
            n, warns = import_file(f)
            ok += 1
            print(f"[OK] {f.name}: {n}행 적재")
            report_lines.append(f"- OK {f.name}: {n}행")
            for w in warns:
                print(f"     경고: {w}")
                report_lines.append(f"  - 경고: {w}")
        except ParseError as e:
            fail += 1
            print(f"[실패] {f.name}: {e}")
            report_lines.append(f"- 실패 {f.name}: {e}")
    for s in skipped:
        print(f"[건너뜀] {s}: 파일명 형식이 맞지 않음")
        report_lines.append(f"- 건너뜀 {s}: 파일명 형식 불일치")

    if not files:
        print(f"임포트할 파일이 없습니다. {MANUAL_DIR} 에 저장해 주세요.")
        return 0

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    (LOG_DIR / f"oy_import_{datetime.now():%Y%m%d_%H%M%S}.md").write_text(
        "\n".join(report_lines), encoding="utf-8"
    )
    print(f"\n완료: 성공 {ok} / 실패 {fail} / 건너뜀 {len(skipped)}")
    return 0 if fail == 0 else 1
