"""공통 테스트 fixture"""

import pytest

from utils import BookInfo, ConfigRecord, OrderRecord


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
