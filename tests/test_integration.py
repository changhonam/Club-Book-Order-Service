"""통합 테스트 — 비즈니스 플로우 시나리오 기반

UI(Streamlit) 레이어는 제외하고 utils 레이어의 함수 조합을 테스트한다.
sheets.py 함수는 Google Sheets mock, scraper.py 함수는 requests mock 처리.
settlement.py 함수는 순수 함수이므로 mock 불필요.
"""

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# --- 모듈 import 전 streamlit mock 설정 (test_sheets.py 패턴 동일) ---

_mock_st = MagicMock()


def _passthrough_cache_data(**kwargs):
    def decorator(func):
        func.clear = MagicMock()
        return func

    return decorator


def _passthrough_cache_resource(func):
    func.clear = MagicMock()
    return func


_mock_st.cache_data = _passthrough_cache_data
_mock_st.cache_resource = _passthrough_cache_resource
_mock_st.secrets = {
    "gcp_service_account": {"type": "service_account"},
    "spreadsheet": {"name": "TestSpreadsheet"},
}

sys.modules["streamlit"] = _mock_st

import requests as requests_lib  # noqa: E402

from utils import OrderRecord  # noqa: E402
from utils.scraper import ScrapingError, scrape_book_info  # noqa: E402
from utils.settlement import (  # noqa: E402
    calculate_monthly_payment,
    calculate_per_order_breakdown,
)
from utils.sheets import (  # noqa: E402
    add_order,
    delete_order,
    find_member,
    get_config,
    get_orders_by_member,
    update_config,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _load_fixture(filename: str) -> str:
    return (FIXTURES_DIR / filename).read_text(encoding="utf-8")


def _mock_response(html: str, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = html
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests_lib.exceptions.HTTPError(
            f"{status_code} Error"
        )
    return resp


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_spreadsheet():
    """gspread 스프레드시트 mock — test_sheets.py 패턴과 동일."""
    with patch("utils.sheets._get_spreadsheet") as mock_get_ss:
        mock_ss = MagicMock()
        mock_get_ss.return_value = mock_ss

        mock_members_ws = MagicMock()
        mock_orders_ws = MagicMock()
        mock_config_ws = MagicMock()
        mock_logs_ws = MagicMock()

        def get_worksheet(name):
            mapping = {
                "Members": mock_members_ws,
                "Orders": mock_orders_ws,
                "Config": mock_config_ws,
                "Logs": mock_logs_ws,
            }
            return mapping[name]

        mock_ss.worksheet.side_effect = get_worksheet

        yield {
            "spreadsheet": mock_ss,
            "members": mock_members_ws,
            "orders": mock_orders_ws,
            "config": mock_config_ws,
            "logs": mock_logs_ws,
        }


def _config_records(
    month: str = "2026-03",
    is_closed: str = "false",
    auto_close_datetime: str = "",
) -> list[dict]:
    return [
        {"Key": "current_order_month", "Value": month},
        {"Key": "is_closed", "Value": is_closed},
        {"Key": "auto_close_datetime", "Value": auto_close_datetime},
    ]


# ===========================================================================
# 시나리오 1: 일반 회원 주문 플로우
# ===========================================================================
class TestMemberOrderFlow:
    """일반 회원이 도서를 검색하고 주문한 뒤, 정산을 확인하고 삭제하는 플로우."""

    def test_full_order_lifecycle(self, mock_spreadsheet):
        """회원 확인 → 설정 조회 → 스크래핑 → 주문 추가 → 주문 조회 → 정산 → 삭제."""
        # 1. 회원 존재 확인
        mock_spreadsheet["members"].col_values.return_value = [
            "Name",
            "홍길동",
            "김철수",
        ]
        assert find_member("홍길동") is True

        # 2. 설정 조회 — 주문 가능 상태
        mock_spreadsheet["config"].get_all_records.return_value = _config_records()
        config = get_config()
        assert config.current_order_month == "2026-03"
        assert config.is_closed is False

        # 3. 도서 스크래핑
        url = "https://www.yes24.com/Product/Goods/91288143"
        with patch("utils.scraper.requests.get") as mock_get:
            html = _load_fixture("yes24_normal.html")
            mock_get.return_value = _mock_response(html)
            book = scrape_book_info(url)

        assert book.is_available is True
        assert book.title == "클린 코드 Clean Code"
        assert book.price == 29700

        # 4. 주문 추가
        with (
            patch("utils.sheets.uuid.uuid4") as mock_uuid,
            patch("utils.sheets.datetime") as mock_dt,
        ):
            mock_uuid.return_value = "integ-uuid-0001"
            mock_dt.now.return_value.strftime.return_value = "2026-03-15 10:30:00"
            order = add_order(
                name="홍길동",
                month="2026-03",
                book_url=book.url,
                title=book.title,
                author=book.author,
                price=book.price,
            )

        assert isinstance(order, OrderRecord)
        assert order.order_id == "integ-uuid-0001"
        assert order.name == "홍길동"
        assert order.price == 29700

        # 5. 주문 조회
        mock_spreadsheet["orders"].get_all_records.return_value = [
            {
                "Order_ID": "integ-uuid-0001",
                "Order_Month": "2026-03",
                "Name": "홍길동",
                "Book_URL": book.url,
                "Title": book.title,
                "Author": book.author,
                "Price": book.price,
                "Created_At": "2026-03-15 10:30:00",
            }
        ]
        orders = get_orders_by_member("홍길동", "2026-03")
        assert len(orders) == 1
        assert orders[0].title == "클린 코드 Clean Code"

        # 6. 정산 확인
        total = sum(o.price for o in orders)
        settlement = calculate_monthly_payment(total)
        assert settlement.total_price == 29700
        # 지원금 = floor(min(29700/2, 30000)) = floor(14850) = 14850
        assert settlement.club_support == 14850
        assert settlement.user_payment == 29700 - 14850

        # 7. 주문 삭제
        mock_cell = MagicMock()
        mock_cell.row = 2
        mock_spreadsheet["orders"].find.return_value = mock_cell
        assert delete_order("integ-uuid-0001") is True
        mock_spreadsheet["orders"].delete_rows.assert_called_once_with(2)


# ===========================================================================
# 시나리오 2: 관리자 마감 관리
# ===========================================================================
class TestAdminCloseManagement:
    """관리자가 마감 상태를 제어하고, 마감 중에도 대리 주문을 추가하는 플로우."""

    def test_close_and_reopen(self, mock_spreadsheet):
        """마감 설정 → 마감 중 대리 주문 → 마감 해제."""
        # 1. 마감 설정
        mock_spreadsheet["config"].get_all_records.return_value = _config_records()
        update_config(is_closed=True)
        mock_spreadsheet["config"].update_cell.assert_called_with(3, 2, "true")

        # 2. 마감 상태에서도 관리자 대리 신청 가능 (add_order는 is_closed를 체크하지 않음)
        with (
            patch("utils.sheets.uuid.uuid4") as mock_uuid,
            patch("utils.sheets.datetime") as mock_dt,
        ):
            mock_uuid.return_value = "admin-proxy-uuid"
            mock_dt.now.return_value.strftime.return_value = "2026-03-20 15:00:00"
            order = add_order(
                name="김철수",
                month="2026-03",
                book_url="https://www.yes24.com/Product/Goods/12345678",
                title="대리 신청 도서",
                author="저자X",
                price=18000,
            )

        assert isinstance(order, OrderRecord)
        assert order.name == "김철수"
        assert order.title == "대리 신청 도서"

        # 3. 마감 해제
        mock_spreadsheet["config"].get_all_records.return_value = _config_records(
            is_closed="true"
        )
        update_config(is_closed=False)
        # update_cell 호출 이력 중 마지막 호출이 false 설정
        last_call = mock_spreadsheet["config"].update_cell.call_args
        assert last_call[0] == (3, 2, "false")


# ===========================================================================
# 시나리오 3: 자동마감 검증
# ===========================================================================
class TestAutoClose:
    """자동마감 datetime이 설정된 경우, 현재 시간이 지정 시간 이후이면 마감 처리."""

    def test_auto_close_triggers_when_past_deadline(self, mock_spreadsheet):
        """자동마감 시간이 지나면 is_closed=True로 전환."""
        # 설정: auto_close_datetime = "2026-03-20 18:00"
        mock_spreadsheet["config"].get_all_records.return_value = _config_records(
            auto_close_datetime="2026-03-20 18:00"
        )
        config = get_config()
        assert config.auto_close_datetime == "2026-03-20 18:00"
        assert config.is_closed is False

        # app.py의 자동마감 로직을 직접 재현
        auto_close_dt = datetime.strptime(config.auto_close_datetime, "%Y-%m-%d %H:%M")
        # 현재 시간을 마감 시간 이후로 설정
        fake_now = datetime(2026, 3, 20, 18, 30)
        assert fake_now >= auto_close_dt

        # 마감 처리 수행
        if fake_now >= auto_close_dt and not config.is_closed:
            mock_spreadsheet["config"].get_all_records.return_value = _config_records(
                auto_close_datetime="2026-03-20 18:00"
            )
            update_config(is_closed=True)

        mock_spreadsheet["config"].update_cell.assert_called_with(3, 2, "true")

    def test_auto_close_does_not_trigger_before_deadline(self, mock_spreadsheet):
        """자동마감 시간 전이면 마감하지 않음."""
        mock_spreadsheet["config"].get_all_records.return_value = _config_records(
            auto_close_datetime="2026-03-20 18:00"
        )
        config = get_config()

        auto_close_dt = datetime.strptime(config.auto_close_datetime, "%Y-%m-%d %H:%M")
        fake_now = datetime(2026, 3, 20, 17, 30)
        assert fake_now < auto_close_dt

        # 마감 처리하지 않아야 함
        should_close = fake_now >= auto_close_dt and not config.is_closed
        assert should_close is False

    def test_auto_close_skips_when_already_closed(self, mock_spreadsheet):
        """이미 마감 상태이면 자동마감 로직을 건너뜀."""
        mock_spreadsheet["config"].get_all_records.return_value = _config_records(
            is_closed="true",
            auto_close_datetime="2026-03-20 18:00",
        )
        config = get_config()
        assert config.is_closed is True

        auto_close_dt = datetime.strptime(config.auto_close_datetime, "%Y-%m-%d %H:%M")
        fake_now = datetime(2026, 3, 21, 10, 0)

        should_close = (
            config.auto_close_datetime
            and not config.is_closed
            and fake_now >= auto_close_dt
        )
        assert should_close is False


# ===========================================================================
# 시나리오 4: 정산 정확성
# ===========================================================================
class TestSettlementAccuracy:
    """다건 주문에 대한 정산 계산 및 비율 분배 정확성 검증."""

    def _make_orders(self, prices: list[int]) -> list[OrderRecord]:
        return [
            OrderRecord(
                order_id=f"settle-{i}",
                order_month="2026-03",
                name="홍길동",
                book_url=f"https://www.yes24.com/Product/Goods/{10000 + i}",
                title=f"도서{i}",
                author=f"저자{i}",
                price=price,
                created_at=f"2026-03-{10 + i} 09:00:00",
            )
            for i, price in enumerate(prices)
        ]

    def test_three_orders_settlement(self):
        """3개 주문 (15000+25000+20000=60000) 정산."""
        total = 60000
        settlement = calculate_monthly_payment(total)

        assert settlement.total_price == 60000
        # 지원금 = floor(min(60000/2, 30000)) = floor(30000) = 30000
        assert settlement.club_support == 30000
        assert settlement.user_payment == 30000

    def test_per_order_breakdown_sum_matches(self):
        """비율 분배 후 support 합산 = club_support, payment 합산 = user_payment."""
        orders = self._make_orders([15000, 25000, 20000])
        breakdown = calculate_per_order_breakdown(orders)

        assert len(breakdown) == 3

        total_support = sum(b["support"] for b in breakdown)
        total_payment = sum(b["payment"] for b in breakdown)

        settlement = calculate_monthly_payment(60000)
        assert total_support == settlement.club_support
        assert total_payment == settlement.user_payment

    def test_per_order_breakdown_price_matches(self):
        """각 주문의 support + payment = 원래 price."""
        orders = self._make_orders([15000, 25000, 20000])
        breakdown = calculate_per_order_breakdown(orders)

        for b, order in zip(breakdown, orders):
            assert b["support"] + b["payment"] == order.price
            assert b["order_id"] == order.order_id

    def test_settlement_below_cap(self):
        """지원금 상한(30000) 이하일 때 50% 지원."""
        settlement = calculate_monthly_payment(40000)
        assert settlement.club_support == 20000
        assert settlement.user_payment == 20000

    def test_settlement_above_cap(self):
        """지원금 상한(30000) 초과 시 상한 적용."""
        settlement = calculate_monthly_payment(80000)
        assert settlement.club_support == 30000
        assert settlement.user_payment == 50000

    def test_settlement_zero(self):
        """총액 0원 정산."""
        settlement = calculate_monthly_payment(0)
        assert settlement.club_support == 0
        assert settlement.user_payment == 0

    def test_per_order_breakdown_empty_list(self):
        """빈 주문 목록 분배."""
        assert calculate_per_order_breakdown([]) == []

    def test_per_order_breakdown_single_order(self):
        """단건 주문 분배 — 오차 흡수 없이 정확."""
        orders = self._make_orders([50000])
        breakdown = calculate_per_order_breakdown(orders)
        assert len(breakdown) == 1
        assert breakdown[0]["support"] == 25000  # floor(min(50000/2, 30000))
        assert breakdown[0]["payment"] == 25000


# ===========================================================================
# 시나리오 5: 스크래핑 실패 처리
# ===========================================================================
class TestScrapingFailures:
    """스크래핑 실패 케이스: 품절, eBook, 잘못된 URL."""

    @patch("utils.scraper.requests.get")
    def test_soldout_book_unavailable(self, mock_get):
        """품절 도서 → is_available=False, reason='품절'."""
        html = _load_fixture("yes24_soldout.html")
        mock_get.return_value = _mock_response(html)

        book = scrape_book_info("https://www.yes24.com/Product/Goods/55555555")

        assert book.is_available is False
        assert book.unavailable_reason == "품절"
        assert book.title == "오래된 소설책"

    @patch("utils.scraper.requests.get")
    def test_ebook_unavailable(self, mock_get):
        """eBook → is_available=False, reason='eBook'."""
        html = _load_fixture("yes24_ebook.html")
        mock_get.return_value = _mock_response(html)

        book = scrape_book_info("https://www.yes24.com/Product/Goods/77777777")

        assert book.is_available is False
        assert book.unavailable_reason == "eBook"

    def test_invalid_url_raises_scraping_error(self):
        """잘못된 도메인 URL → ScrapingError."""
        with pytest.raises(ScrapingError):
            scrape_book_info("https://www.kyobobooks.co.kr/product/1234")

    @patch("utils.scraper.requests.get")
    def test_http_error_raises_scraping_error(self, mock_get):
        """HTTP 404 → ScrapingError."""
        mock_get.return_value = _mock_response("", status_code=404)

        with pytest.raises(ScrapingError, match="HTTP 요청 실패"):
            scrape_book_info("https://www.yes24.com/Product/Goods/99999999")

    @patch("utils.scraper.requests.get")
    def test_timeout_raises_scraping_error(self, mock_get):
        """타임아웃 → ScrapingError."""
        mock_get.side_effect = requests_lib.exceptions.Timeout("timeout")

        with pytest.raises(ScrapingError, match="시간 초과"):
            scrape_book_info("https://www.yes24.com/Product/Goods/99999999")

    @patch("utils.scraper.requests.get")
    def test_scrape_then_settlement_integration(self, mock_get):
        """정상 스크래핑 결과를 정산에 연결하는 end-to-end 확인."""
        html = _load_fixture("yes24_normal.html")
        mock_get.return_value = _mock_response(html)

        book = scrape_book_info("https://www.yes24.com/Product/Goods/91288143")
        assert book.is_available is True

        settlement = calculate_monthly_payment(book.price)
        assert settlement.total_price == book.price
        assert settlement.club_support + settlement.user_payment == book.price
