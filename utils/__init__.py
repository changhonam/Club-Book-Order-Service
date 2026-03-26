from dataclasses import dataclass
from typing import Optional


@dataclass
class BookInfo:
    """Yes24에서 스크래핑한 도서 정보"""

    title: str
    author: str
    publisher: str
    price: int  # 판매가 (원)
    url: str  # 정규화된 www.yes24.com URL
    is_available: bool  # 구매 가능 여부
    unavailable_reason: Optional[str] = None  # "품절", "절판", "eBook" 등


@dataclass
class Settlement:
    """월별 정산 결과"""

    total_price: int  # 월 총 주문금액
    club_support: int  # 동호회 지원금: floor(min(총액/2, 30000))
    user_payment: int  # 본인 부담금: 총액 - club_support


@dataclass
class OrderRecord:
    """주문 레코드"""

    order_id: str  # UUID4
    order_month: str  # "YYYY-MM"
    name: str  # 신청자 이름
    book_url: str
    title: str
    author: str
    price: int
    created_at: str  # "YYYY-MM-DD HH:MM:SS"


@dataclass
class ConfigRecord:
    """서비스 설정"""

    current_order_month: str  # "YYYY-MM"
    is_closed: bool
    auto_close_datetime: Optional[str] = None  # "YYYY-MM-DD HH:MM" 또는 None
