"""정산 로직 모듈"""

import math

from utils import OrderRecord, Settlement


def calculate_monthly_payment(monthly_total_price: int) -> Settlement:
    """월 총액 기반 정산 계산.

    동호회 지원금 = floor(min(총액/2, 30000))
    본인 부담금 = 총액 - 지원금

    Raises:
        ValueError: 음수 입력 시
    """
    if monthly_total_price < 0:
        raise ValueError("monthly_total_price must be non-negative")

    club_support = math.floor(min(monthly_total_price / 2, 30000))
    user_payment = monthly_total_price - club_support

    return Settlement(
        total_price=monthly_total_price,
        club_support=club_support,
        user_payment=user_payment,
    )


def calculate_per_order_breakdown(
    orders: list[OrderRecord],
) -> list[dict]:
    """주문별 부담금 비율 분배.

    각 주문의 가격 비율에 따라 지원금/부담금을 분배한다.
    반올림 오차는 마지막 항목에서 흡수하여 합산이 정확히 일치하도록 한다.

    Returns:
        [{"order_id", "price", "support", "payment"}, ...]
    """
    if not orders:
        return []

    total_price = sum(o.price for o in orders)
    settlement = calculate_monthly_payment(total_price)

    result: list[dict] = []
    allocated_support = 0

    for i, order in enumerate(orders):
        if i < len(orders) - 1:
            # 비율에 따라 지원금 분배 (반올림)
            support = round(settlement.club_support * order.price / total_price)
            allocated_support += support
        else:
            # 마지막 항목: 오차 흡수
            support = settlement.club_support - allocated_support

        payment = order.price - support
        result.append(
            {
                "order_id": order.order_id,
                "price": order.price,
                "support": support,
                "payment": payment,
            }
        )

    return result
