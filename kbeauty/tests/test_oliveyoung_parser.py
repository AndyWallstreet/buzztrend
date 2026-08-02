"""올리브영 수동 저장 파서 테스트.

fixture는 2026-07-31 실제 스킨케어 랭킹 페이지에서 추출한 상품 목록 HTML.
"""
from datetime import date
from pathlib import Path

import pytest

from etl.oliveyoung_manual import parse_file, validate, ParseError

FIXTURE = Path(__file__).parent / "fixtures" / "oliveyoung_skincare_2026-07-31.html"


@pytest.fixture(scope="module")
def rows():
    return parse_file(FIXTURE, date(2026, 7, 31), "스킨케어")


def test_100_products(rows):
    assert len(rows) == 100


def test_ranks_contiguous(rows):
    assert sorted(r.rank for r in rows) == list(range(1, 101))


def test_rank1_fields(rows):
    r1 = next(r for r in rows if r.rank == 1)
    assert r1.brand == "온그리디언츠"
    assert "바쿠글로우 캡슐 로션" in r1.product_name
    assert r1.goods_no and r1.goods_no.startswith("A")
    assert r1.product_category_path and "스킨케어" in r1.product_category_path


def test_prices_parsed(rows):
    # 모든 상품에 현재가가 있어야 하고, 할인 상품은 원가 > 현재가
    assert all(r.price_current is not None for r in rows)
    discounted = [r for r in rows if r.price_original is not None]
    assert discounted, "샘플에 할인 상품이 있어야 함"
    assert all(r.price_original > r.price_current for r in discounted)


def test_no_fabrication(rows):
    # 빠진 값은 NULL(None)로 남아야지, 채워 넣으면 안 됨
    for r in rows:
        assert r.rating is None or 0 <= r.rating <= 10


def test_validate_passes(rows):
    warnings = []
    validate(rows, warnings)


def test_validate_rejects_truncated(rows):
    with pytest.raises(ParseError):
        validate(rows[:50], [])
