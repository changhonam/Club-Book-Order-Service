"""Google Sheets CRUD 모듈 테스트

streamlit mock은 conftest.py에서 설정한다.
"""

from unittest.mock import MagicMock, patch

import gspread
import gspread.exceptions
import pytest

import utils.sheets as _sheets_mod
from utils import ConfigRecord, MemberRecord, OrderRecord
from utils.sheets import (
    add_member,
    add_order,
    append_log,
    clear_config_cache,
    clear_member_cache,
    clear_order_cache,
    delete_order,
    delete_orders_by_month,
    find_member,
    get_all_members,
    get_config,
    get_existing_order_months,
    get_orders_by_member,
    get_orders_by_month,
    get_recent_logs,
    remove_member,
    update_config,
    with_retry,
)

# _get_all_orders_raw 참조 (private이라 ruff가 직접 import를 제거하므로 모듈 경유)
_get_all_orders_raw = _sheets_mod._get_all_orders_raw


# --- Fixtures ---


@pytest.fixture
def mock_spreadsheet():
    """gspread 스프레드시트 mock."""
    with patch("utils.sheets._get_spreadsheet") as mock_get_ss:
        mock_ss = MagicMock()
        mock_get_ss.return_value = mock_ss

        # 각 워크시트 mock 설정
        mock_members_ws = MagicMock()
        mock_orders_ws = MagicMock()
        mock_config_ws = MagicMock()
        mock_logs_ws = MagicMock()
        # fee_paid가 MembershipFees에서 파생되므로 회원을 읽을 때마다 함께 조회된다
        mock_fee_ws = MagicMock()
        mock_fee_ws.get_all_records.return_value = []

        def get_worksheet(name):
            mapping = {
                "Members": mock_members_ws,
                "Orders": mock_orders_ws,
                "Config": mock_config_ws,
                "Logs": mock_logs_ws,
                "MembershipFees": mock_fee_ws,
            }
            return mapping[name]

        mock_ss.worksheet.side_effect = get_worksheet

        yield {
            "spreadsheet": mock_ss,
            "members": mock_members_ws,
            "orders": mock_orders_ws,
            "config": mock_config_ws,
            "logs": mock_logs_ws,
            "fees": mock_fee_ws,
        }


# --- Members 테스트 ---


class TestMembers:
    def test_get_all_members(self, mock_spreadsheet):
        """회원 전체 목록 조회. fee_paid는 현재 분기 회비 기록에서 파생."""
        mock_spreadsheet["config"].get_all_records.return_value = [
            {"Key": "current_order_month", "Value": "2026-03"},
        ]
        mock_spreadsheet["members"].get_all_records.return_value = [
            {"Name": "홍길동", "PIN": "1234", "Fee_Paid": "true"},
            {"Name": "김철수", "PIN": "0000", "Fee_Paid": "false"},
        ]
        mock_spreadsheet["fees"].get_all_records.return_value = [
            {"Name": "홍길동", "Quarter": "2026-Q1", "Paid_At": ""},
        ]
        result = get_all_members()
        assert all(isinstance(m, MemberRecord) for m in result)
        assert [m.name for m in result] == ["홍길동", "김철수"]
        assert result[0].pin == "1234"
        assert result[0].fee_paid is True
        assert result[1].fee_paid is False

    def test_get_all_members_empty(self, mock_spreadsheet):
        """빈 회원 목록."""
        mock_spreadsheet["members"].get_all_records.return_value = []
        result = get_all_members()
        assert result == []

    def test_find_member_exists(self, mock_spreadsheet):
        """존재하는 회원 검색."""
        mock_spreadsheet["members"].get_all_records.return_value = [
            {"Name": "홍길동", "PIN": "1234", "Fee_Paid": "true"},
            {"Name": "김철수", "PIN": "0000", "Fee_Paid": "false"},
        ]
        result = find_member("홍길동")
        assert result is not None
        assert result.name == "홍길동"
        assert result.pin == "1234"

    def test_find_member_not_exists(self, mock_spreadsheet):
        """존재하지 않는 회원 검색."""
        mock_spreadsheet["members"].get_all_records.return_value = [
            {"Name": "홍길동", "PIN": "0000", "Fee_Paid": "false"},
        ]
        assert find_member("이영희") is None

    def test_add_member_success(self, mock_spreadsheet):
        """회원 추가 성공."""
        mock_spreadsheet["members"].get_all_records.return_value = [
            {"Name": "홍길동", "PIN": "0000", "Fee_Paid": "false"},
        ]
        result = add_member("김철수")
        assert result is True
        # 신규 회원은 현재 분기 회비를 납부한 것으로 간주하므로 미러도 "true"
        mock_spreadsheet["members"].append_row.assert_called_once_with(
            ["김철수", "0000", "true"], value_input_option="RAW"
        )

    def test_add_member_duplicate(self, mock_spreadsheet):
        """중복 회원 추가 -> False."""
        mock_spreadsheet["members"].get_all_records.return_value = [
            {"Name": "홍길동", "PIN": "0000", "Fee_Paid": "false"},
        ]
        result = add_member("홍길동")
        assert result is False
        mock_spreadsheet["members"].append_row.assert_not_called()

    def test_remove_member_success(self, mock_spreadsheet):
        """회원 삭제 성공."""
        mock_cell = MagicMock()
        mock_cell.row = 3
        mock_spreadsheet["members"].find.return_value = mock_cell
        result = remove_member("김철수")
        assert result is True
        mock_spreadsheet["members"].delete_rows.assert_called_once_with(3)

    def test_remove_member_not_found(self, mock_spreadsheet):
        """없는 회원 삭제 -> False."""
        mock_spreadsheet["members"].find.return_value = None
        result = remove_member("없는사람")
        assert result is False
        mock_spreadsheet["members"].delete_rows.assert_not_called()


# --- Orders 테스트 ---


class TestOrders:
    def _make_order_records(self):
        return [
            {
                "Order_ID": "id-1",
                "Order_Month": "2026-03",
                "Name": "홍길동",
                "Book_URL": "https://www.yes24.com/Product/Goods/11111111",
                "Title": "도서A",
                "Author": "저자A",
                "Price": 30000,
                "Created_At": "2026-03-10 09:00:00",
                "Publisher": "출판사A",
                "ISBN": "9788966260001",
            },
            {
                "Order_ID": "id-2",
                "Order_Month": "2026-03",
                "Name": "김철수",
                "Book_URL": "https://www.yes24.com/Product/Goods/22222222",
                "Title": "도서B",
                "Author": "저자B",
                "Price": 20000,
                "Created_At": "2026-03-11 14:00:00",
                "Publisher": "출판사B",
                "ISBN": "9788966260002",
            },
            {
                "Order_ID": "id-3",
                "Order_Month": "2026-02",
                "Name": "홍길동",
                "Book_URL": "https://www.yes24.com/Product/Goods/33333333",
                "Title": "도서C",
                "Author": "저자C",
                "Price": 15000,
                "Created_At": "2026-02-10 09:00:00",
                "Publisher": "출판사C",
                "ISBN": "9788966260003",
            },
        ]

    def test_get_orders_by_month(self, mock_spreadsheet):
        """월별 주문 조회."""
        mock_spreadsheet[
            "orders"
        ].get_all_records.return_value = self._make_order_records()
        result = get_orders_by_month("2026-03")
        assert len(result) == 2
        assert all(isinstance(r, OrderRecord) for r in result)
        assert result[0].order_id == "id-1"
        assert result[0].publisher == "출판사A"
        assert result[0].isbn == "9788966260001"
        assert result[1].order_id == "id-2"

    def test_get_orders_by_month_empty(self, mock_spreadsheet):
        """해당 월 주문 없음."""
        mock_spreadsheet[
            "orders"
        ].get_all_records.return_value = self._make_order_records()
        result = get_orders_by_month("2026-04")
        assert result == []

    def test_get_orders_by_member(self, mock_spreadsheet):
        """회원별 주문 조회."""
        mock_spreadsheet[
            "orders"
        ].get_all_records.return_value = self._make_order_records()
        result = get_orders_by_member("홍길동", "2026-03")
        assert len(result) == 1
        assert result[0].name == "홍길동"
        assert result[0].order_month == "2026-03"

    def test_add_order(self, mock_spreadsheet):
        """주문 추가 - UUID 및 타임스탬프 검증."""
        with (
            patch("utils.sheets.uuid.uuid4") as mock_uuid,
            patch("utils.sheets.datetime") as mock_dt,
        ):
            mock_uuid.return_value = "test-uuid-1234"
            mock_dt.now.return_value.strftime.return_value = "2026-03-15 10:30:00"

            result = add_order(
                name="홍길동",
                month="2026-03",
                book_url="https://www.yes24.com/Product/Goods/12345678",
                title="테스트 도서",
                author="테스트 저자",
                price=15000,
                publisher="테스트출판사",
                isbn="9788966260959",
            )

        assert isinstance(result, OrderRecord)
        assert result.order_id == "test-uuid-1234"
        assert result.created_at == "2026-03-15 10:30:00"
        assert result.name == "홍길동"
        assert result.price == 15000
        assert result.publisher == "테스트출판사"
        assert result.isbn == "9788966260959"
        mock_spreadsheet["orders"].append_row.assert_called_once_with(
            [
                "test-uuid-1234",
                "2026-03",
                "홍길동",
                "https://www.yes24.com/Product/Goods/12345678",
                "테스트 도서",
                "테스트 저자",
                "테스트출판사",
                "9788966260959",
                15000,
                "2026-03-15 10:30:00",
            ]
        )

    def test_delete_order_success(self, mock_spreadsheet):
        """주문 삭제 성공."""
        mock_cell = MagicMock()
        mock_cell.row = 5
        mock_spreadsheet["orders"].find.return_value = mock_cell
        result = delete_order("id-1")
        assert result is True
        mock_spreadsheet["orders"].delete_rows.assert_called_once_with(5)

    def test_delete_order_not_found(self, mock_spreadsheet):
        """없는 주문 삭제 -> False."""
        mock_spreadsheet["orders"].find.return_value = None
        result = delete_order("nonexistent-id")
        assert result is False

    def test_delete_orders_by_month(self, mock_spreadsheet):
        """월별 일괄 삭제."""
        mock_spreadsheet[
            "orders"
        ].get_all_records.return_value = self._make_order_records()
        result = delete_orders_by_month("2026-03")
        assert result == 2
        # 역순으로 삭제 확인 (row 3 먼저, 그 다음 row 2)
        calls = mock_spreadsheet["orders"].delete_rows.call_args_list
        assert len(calls) == 2
        assert calls[0][0][0] == 3  # idx=1 -> row 3
        assert calls[1][0][0] == 2  # idx=0 -> row 2

    def test_delete_orders_by_month_none(self, mock_spreadsheet):
        """삭제할 주문 없음."""
        mock_spreadsheet[
            "orders"
        ].get_all_records.return_value = self._make_order_records()
        result = delete_orders_by_month("2026-04")
        assert result == 0

    def test_get_orders_by_month_backward_compat(self, mock_spreadsheet):
        """Publisher/ISBN 컬럼 없는 기존 데이터 하위호환."""
        old_records = [
            {
                "Order_ID": "id-old",
                "Order_Month": "2026-01",
                "Name": "홍길동",
                "Book_URL": "https://www.yes24.com/Product/Goods/99999999",
                "Title": "구버전 도서",
                "Author": "저자X",
                "Price": 10000,
                "Created_At": "2026-01-01 00:00:00",
            },
        ]
        mock_spreadsheet["orders"].get_all_records.return_value = old_records
        result = get_orders_by_month("2026-01")
        assert len(result) == 1
        assert result[0].publisher == ""
        assert result[0].isbn == ""

    def test_get_existing_order_months(self, mock_spreadsheet):
        """주문이 존재하는 월 집합 반환."""
        mock_spreadsheet[
            "orders"
        ].get_all_records.return_value = self._make_order_records()
        result = get_existing_order_months()
        assert result == {"2026-03", "2026-02"}

    def test_get_existing_order_months_empty(self, mock_spreadsheet):
        """주문 없을 때 빈 집합."""
        mock_spreadsheet["orders"].get_all_records.return_value = []
        result = get_existing_order_months()
        assert result == set()


# --- Config 테스트 ---


class TestConfig:
    def _config_records(self):
        return [
            {"Key": "current_order_month", "Value": "2026-03"},
            {"Key": "is_closed", "Value": "false"},
            {"Key": "auto_close_datetime", "Value": ""},
        ]

    def test_get_config(self, mock_spreadsheet):
        """설정 조회 - 문자열 -> 타입 변환 검증."""
        mock_spreadsheet["config"].get_all_records.return_value = self._config_records()
        result = get_config()
        assert isinstance(result, ConfigRecord)
        assert result.current_order_month == "2026-03"
        assert result.is_closed is False
        assert result.auto_close_datetime is None

    def test_get_config_closed(self, mock_spreadsheet):
        """is_closed=true 검증."""
        records = self._config_records()
        records[1]["Value"] = "true"
        records[2]["Value"] = "2026-03-25 18:00"
        mock_spreadsheet["config"].get_all_records.return_value = records
        result = get_config()
        assert result.is_closed is True
        assert result.auto_close_datetime == "2026-03-25 18:00"

    def test_update_config_partial(self, mock_spreadsheet):
        """부분 업데이트 - is_closed만 변경."""
        mock_spreadsheet["config"].get_all_records.return_value = self._config_records()
        update_config(is_closed=True)
        mock_spreadsheet["config"].update_cell.assert_called_once_with(3, 2, "true")

    def test_update_config_multiple(self, mock_spreadsheet):
        """복수 필드 업데이트."""
        mock_spreadsheet["config"].get_all_records.return_value = self._config_records()
        update_config(current_order_month="2026-04", is_closed=False)
        calls = mock_spreadsheet["config"].update_cell.call_args_list
        assert len(calls) == 2


# --- Logs 테스트 ---


class TestLogs:
    def test_append_log(self, mock_spreadsheet):
        """로그 기록."""
        with patch("utils.sheets.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "2026-03-15 10:30:00"
            append_log("ORDER_CREATE", "주문 생성")
        mock_spreadsheet["logs"].append_row.assert_called_once_with(
            ["2026-03-15 10:30:00", "ORDER_CREATE", "주문 생성"]
        )

    def test_get_recent_logs(self, mock_spreadsheet):
        """최근 로그 조회 - 역순."""
        log_records = [
            {
                "Timestamp": "2026-03-10 09:00:00",
                "Event_Type": "ORDER_CREATE",
                "Message": "msg1",
            },
            {
                "Timestamp": "2026-03-11 10:00:00",
                "Event_Type": "ORDER_DELETE",
                "Message": "msg2",
            },
            {
                "Timestamp": "2026-03-12 11:00:00",
                "Event_Type": "ADMIN_CLOSE_MONTH",
                "Message": "msg3",
            },
        ]
        mock_spreadsheet["logs"].get_all_records.return_value = log_records
        result = get_recent_logs(limit=2)
        assert len(result) == 2
        # 최신이 먼저
        assert result[0]["event_type"] == "ADMIN_CLOSE_MONTH"
        assert result[1]["event_type"] == "ORDER_DELETE"

    def test_get_recent_logs_all(self, mock_spreadsheet):
        """전체 로그 조회 (limit > 전체 건수)."""
        log_records = [
            {
                "Timestamp": "2026-03-10 09:00:00",
                "Event_Type": "ORDER_CREATE",
                "Message": "msg1",
            },
        ]
        mock_spreadsheet["logs"].get_all_records.return_value = log_records
        result = get_recent_logs(limit=50)
        assert len(result) == 1


# --- 재시도 데코레이터 테스트 ---


class TestWithRetry:
    @staticmethod
    def _make_api_error(code=429):
        """gspread APIError를 올바르게 생성."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "error": {"code": code, "message": "error", "status": "ERROR"}
        }
        return gspread.exceptions.APIError(mock_response)

    def test_retry_success_on_second_attempt(self):
        """첫 시도 실패 -> 재시도 성공."""
        call_count = 0

        @with_retry(max_retries=2, base_delay=0)
        def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise self._make_api_error(429)
            return "success"

        result = flaky_func()
        assert result == "success"
        assert call_count == 2

    def test_retry_all_fail(self):
        """모든 재시도 실패 -> 예외 발생."""

        @with_retry(max_retries=2, base_delay=0)
        def always_fail():
            raise self._make_api_error(500)

        with pytest.raises(gspread.exceptions.APIError):
            always_fail()

    def test_no_retry_on_success(self):
        """성공 시 재시도 없음."""
        call_count = 0

        @with_retry(max_retries=2, base_delay=0)
        def good_func():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = good_func()
        assert result == "ok"
        assert call_count == 1


# --- 캐시 헬퍼 테스트 ---


class TestCacheHelpers:
    def test_clear_member_cache(self):
        """회원 캐시 클리어."""
        get_all_members.clear = MagicMock()
        clear_member_cache()
        get_all_members.clear.assert_called_once()

    def test_clear_order_cache(self):
        """주문 캐시 클리어."""
        _get_all_orders_raw.clear = MagicMock()
        get_orders_by_month.clear = MagicMock()
        clear_order_cache()
        _get_all_orders_raw.clear.assert_called_once()
        get_orders_by_month.clear.assert_called_once()

    def test_clear_config_cache(self):
        """설정 캐시 클리어. 접수월이 바뀌면 유효 분기도 바뀌므로 회원 캐시도 함께 비운다."""
        get_config.clear = MagicMock()
        get_all_members.clear = MagicMock()
        clear_config_cache()
        get_config.clear.assert_called_once()
        get_all_members.clear.assert_called_once()

    def test_add_member_clears_cache(self, mock_spreadsheet):
        """회원 추가 후 캐시 클리어 확인."""
        mock_spreadsheet["members"].col_values.return_value = ["Name"]
        get_all_members.clear = MagicMock()
        add_member("새회원")
        get_all_members.clear.assert_called()

    def test_delete_order_clears_cache(self, mock_spreadsheet):
        """주문 삭제 후 캐시 클리어 확인."""
        mock_cell = MagicMock()
        mock_cell.row = 2
        mock_spreadsheet["orders"].find.return_value = mock_cell
        get_orders_by_month.clear = MagicMock()
        delete_order("some-id")
        get_orders_by_month.clear.assert_called()
