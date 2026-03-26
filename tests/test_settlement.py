"""정산 로직 테스트"""

import pytest

from utils import OrderRecord
from utils.settlement import calculate_monthly_payment, calculate_per_order_breakdown


class TestCalculateMonthlyPayment:
    """calculate_monthly_payment 테스트"""

    def test_zero(self):
        result = calculate_monthly_payment(0)
        assert result.total_price == 0
        assert result.club_support == 0
        assert result.user_payment == 0

    def test_small_amount(self):
        """소액: 10,000원 -> 지원금 5,000, 부담금 5,000"""
        result = calculate_monthly_payment(10000)
        assert result.club_support == 5000
        assert result.user_payment == 5000

    def test_boundary(self):
        """경계값: 60,000원 -> 지원금 30,000, 부담금 30,000"""
        result = calculate_monthly_payment(60000)
        assert result.club_support == 30000
        assert result.user_payment == 30000

    def test_over_cap(self):
        """초과: 100,000원 -> 지원금 30,000, 부담금 70,000"""
        result = calculate_monthly_payment(100000)
        assert result.club_support == 30000
        assert result.user_payment == 70000

    def test_odd_amount(self):
        """홀수: 59,999원 -> 지원금 29,999, 부담금 30,000"""
        result = calculate_monthly_payment(59999)
        assert result.club_support == 29999
        assert result.user_payment == 30000

    def test_negative_raises(self):
        """음수 입력 시 ValueError"""
        with pytest.raises(ValueError):
            calculate_monthly_payment(-1000)


class TestCalculatePerOrderBreakdown:
    """calculate_per_order_breakdown 테스트"""

    def test_empty_list(self):
        assert calculate_per_order_breakdown([]) == []

    def test_two_orders_breakdown(self, sample_orders_for_settlement):
        """2건 혼합 (30,000 + 40,000 = 70,000) -> 비율 분배, 합산 일치"""
        result = calculate_per_order_breakdown(sample_orders_for_settlement)

        assert len(result) == 2

        # 총액 70,000 -> 지원금 30,000, 부담금 40,000
        total_support = sum(r["support"] for r in result)
        total_payment = sum(r["payment"] for r in result)

        assert total_support == 30000
        assert total_payment == 40000

        # 각 주문의 support + payment == price
        for r in result:
            assert r["support"] + r["payment"] == r["price"]

        # order_id 확인
        assert result[0]["order_id"] == "id-1"
        assert result[1]["order_id"] == "id-2"

        # 비율 분배 확인: 30000/70000 * 30000 ≈ 12857
        assert result[0]["price"] == 30000
        assert result[1]["price"] == 40000

    def test_single_order(self):
        """단일 주문: 지원금 전액 해당 주문에 배분"""
        orders = [
            OrderRecord(
                order_id="single",
                order_month="2026-03",
                name="홍길동",
                book_url="https://www.yes24.com/Product/Goods/11111111",
                title="도서A",
                author="저자A",
                price=50000,
                created_at="2026-03-10 09:00:00",
            ),
        ]
        result = calculate_per_order_breakdown(orders)

        assert len(result) == 1
        assert result[0]["support"] == 25000  # floor(min(50000/2, 30000))
        assert result[0]["payment"] == 25000

    def test_rounding_error_absorbed_by_last(self):
        """반올림 오차가 마지막 항목에서 흡수되는지 확인"""
        orders = [
            OrderRecord(
                order_id="a",
                order_month="2026-03",
                name="홍길동",
                book_url="url1",
                title="A",
                author="X",
                price=10000,
                created_at="2026-03-01 00:00:00",
            ),
            OrderRecord(
                order_id="b",
                order_month="2026-03",
                name="홍길동",
                book_url="url2",
                title="B",
                author="Y",
                price=10000,
                created_at="2026-03-01 00:00:00",
            ),
            OrderRecord(
                order_id="c",
                order_month="2026-03",
                name="홍길동",
                book_url="url3",
                title="C",
                author="Z",
                price=10000,
                created_at="2026-03-01 00:00:00",
            ),
        ]
        result = calculate_per_order_breakdown(orders)

        total_support = sum(r["support"] for r in result)
        total_payment = sum(r["payment"] for r in result)

        # 총액 30,000 -> 지원금 15,000, 부담금 15,000
        assert total_support == 15000
        assert total_payment == 15000

        for r in result:
            assert r["support"] + r["payment"] == r["price"]
