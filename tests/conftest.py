"""공통 테스트 fixture 및 streamlit mock 설정

utils.sheets는 import 시점에 @st.cache_data / @st.cache_resource 데코레이터를
평가하므로, 그 전에 streamlit을 mock으로 대체해야 한다. conftest.py는 어떤
테스트 모듈보다 먼저 로드되므로 여기서 처리하면 수집 순서와 무관하게 동작한다.
(각 테스트 파일에 두면 mock 없이 utils.sheets를 import하는 파일이 먼저 수집될
경우 실제 캐시가 걸려 원인을 찾기 어려운 실패가 난다.)
"""

import sys
from unittest.mock import MagicMock

import pytest


def _passthrough_cache_data(**kwargs):
    """st.cache_data를 투명 데코레이터로 대체."""

    def decorator(func):
        func.clear = MagicMock()
        return func

    return decorator


def _passthrough_cache_resource(func):
    """st.cache_resource를 투명 데코레이터로 대체."""
    func.clear = MagicMock()
    return func


_mock_st = MagicMock()
_mock_st.cache_data = _passthrough_cache_data
_mock_st.cache_resource = _passthrough_cache_resource
_mock_st.secrets = {
    "gcp_service_account": {"type": "service_account"},
    "spreadsheet": {"name": "TestSpreadsheet"},
}

sys.modules["streamlit"] = _mock_st

from utils import BookInfo, ConfigRecord, OrderRecord  # noqa: E402


@pytest.fixture
def sample_book_info():
    return BookInfo(
        title="테스트 도서",
        author="홍길동",
        publisher="테스트출판사",
        price=15000,
        url="https://www.yes24.com/Product/Goods/12345678",
        is_available=True,
        unavailable_reason=None,
        isbn="9788966260959",
    )


@pytest.fixture
def sample_order():
    return OrderRecord(
        order_id="550e8400-e29b-41d4-a716-446655440000",
        order_month="2026-03",
        name="홍길동",
        book_url="https://www.yes24.com/Product/Goods/12345678",
        title="테스트 도서",
        author="홍길동",
        price=15000,
        created_at="2026-03-15 10:30:00",
        publisher="테스트출판사",
        isbn="9788966260959",
    )


@pytest.fixture
def sample_config():
    return ConfigRecord(
        current_order_month="2026-03",
        is_closed=False,
        auto_close_datetime=None,
    )


@pytest.fixture
def sample_orders_for_settlement():
    """정산 테스트용 주문 목록 (총액 70,000원)"""
    return [
        OrderRecord(
            order_id="id-1",
            order_month="2026-03",
            name="홍길동",
            book_url="https://www.yes24.com/Product/Goods/11111111",
            title="도서A",
            author="저자A",
            price=30000,
            created_at="2026-03-10 09:00:00",
            publisher="출판사A",
            isbn="9788966260001",
        ),
        OrderRecord(
            order_id="id-2",
            order_month="2026-03",
            name="홍길동",
            book_url="https://www.yes24.com/Product/Goods/22222222",
            title="도서B",
            author="저자B",
            price=40000,
            created_at="2026-03-11 14:00:00",
            publisher="출판사B",
            isbn="9788966260002",
        ),
    ]
