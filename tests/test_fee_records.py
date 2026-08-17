"""회비 납부 기록(MembershipFees) CRUD 테스트

행의 존재 자체가 '납부'를 의미하고, 회원의 fee_paid는 현재 유효 분기의
기록에서 파생된다는 것이 이 계층의 핵심 계약이다.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from utils import FeeRecord
from utils.sheets import (
    _delete_rows_in_runs,
    _sync_members_fee_paid,
    batch_add_fee_records,
    batch_remove_fee_records,
    clear_fee_cache,
    delete_fee_records_by_quarter,
    get_all_members,
    get_current_fee_quarter,
    get_fee_paid_names,
    get_fee_quarters,
    get_fee_records,
    set_fee_paid,
)

KST = ZoneInfo("Asia/Seoul")


@pytest.fixture
def mock_spreadsheet():
    """gspread 스프레드시트 mock. 접수월 2026-08 → 유효 분기 2026-Q3."""
    with patch("utils.sheets._get_spreadsheet") as mock_get_ss:
        mock_ss = MagicMock()
        mock_get_ss.return_value = mock_ss

        mock_members_ws = MagicMock()
        mock_config_ws = MagicMock()
        mock_fee_ws = MagicMock()

        mock_members_ws.get_all_records.return_value = []
        mock_config_ws.get_all_records.return_value = [
            {"Key": "current_order_month", "Value": "2026-08"},
        ]
        mock_fee_ws.get_all_records.return_value = []

        def get_worksheet(name):
            mapping = {
                "Members": mock_members_ws,
                "Config": mock_config_ws,
                "MembershipFees": mock_fee_ws,
            }
            return mapping[name]

        mock_ss.worksheet.side_effect = get_worksheet

        yield {
            "members": mock_members_ws,
            "config": mock_config_ws,
            "fees": mock_fee_ws,
        }


def _rows(*pairs):
    """(이름, 분기) 튜플들을 MembershipFees 레코드 형태로 변환."""
    return [{"Name": n, "Quarter": q, "Paid_At": ""} for n, q in pairs]


# --- get_current_fee_quarter ---


class TestGetCurrentFeeQuarter:
    def test_derived_from_order_month(self, mock_spreadsheet):
        """접수월에서 분기를 파생한다."""
        assert get_current_fee_quarter() == "2026-Q3"

    def test_falls_back_when_month_empty(self, mock_spreadsheet):
        """접수월이 비면 KST 현재 시각 기준으로 폴백 (예외를 던지지 않는다)."""
        mock_spreadsheet["config"].get_all_records.return_value = []
        with patch("utils.sheets.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 11, 2, tzinfo=KST)
            assert get_current_fee_quarter() == "2026-Q4"

    def test_falls_back_when_month_malformed(self, mock_spreadsheet):
        """접수월 형식이 잘못돼도 폴백한다."""
        mock_spreadsheet["config"].get_all_records.return_value = [
            {"Key": "current_order_month", "Value": "202608"},
        ]
        with patch("utils.sheets.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 10, tzinfo=KST)
            assert get_current_fee_quarter() == "2026-Q1"


# --- 조회 ---


class TestGetFeeRecords:
    def test_all(self, mock_spreadsheet):
        """quarter=None이면 전체 반환."""
        mock_spreadsheet["fees"].get_all_records.return_value = _rows(
            ("홍길동", "2026-Q3"), ("김철수", "2026-Q2")
        )
        result = get_fee_records()
        assert len(result) == 2
        assert all(isinstance(r, FeeRecord) for r in result)

    def test_filtered_by_quarter(self, mock_spreadsheet):
        """분기를 주면 해당 분기만 반환."""
        mock_spreadsheet["fees"].get_all_records.return_value = _rows(
            ("홍길동", "2026-Q3"), ("김철수", "2026-Q2"), ("이영희", "2026-Q3")
        )
        result = get_fee_records("2026-Q3")
        assert [r.name for r in result] == ["홍길동", "이영희"]

    def test_empty_sheet(self, mock_spreadsheet):
        assert get_fee_records() == []

    def test_parses_paid_at(self, mock_spreadsheet):
        mock_spreadsheet["fees"].get_all_records.return_value = [
            {"Name": "홍길동", "Quarter": "2026-Q3", "Paid_At": "2026-07-01 09:00:00"},
        ]
        assert get_fee_records()[0].paid_at == "2026-07-01 09:00:00"


class TestGetFeePaidNames:
    def test_returns_set(self, mock_spreadsheet):
        mock_spreadsheet["fees"].get_all_records.return_value = _rows(
            ("홍길동", "2026-Q3"), ("김철수", "2026-Q2")
        )
        assert get_fee_paid_names("2026-Q3") == {"홍길동"}

    def test_absorbs_duplicate_rows(self, mock_spreadsheet):
        """중복 행이 있어도 집합이라 한 명으로 취급된다."""
        mock_spreadsheet["fees"].get_all_records.return_value = _rows(
            ("홍길동", "2026-Q3"), ("홍길동", "2026-Q3")
        )
        assert get_fee_paid_names("2026-Q3") == {"홍길동"}

    def test_ignores_blank_names(self, mock_spreadsheet):
        mock_spreadsheet["fees"].get_all_records.return_value = _rows(
            ("", "2026-Q3"), ("홍길동", "2026-Q3")
        )
        assert get_fee_paid_names("2026-Q3") == {"홍길동"}


class TestGetFeeQuarters:
    def test_descending_unique(self, mock_spreadsheet):
        """중복 없이 최신순으로 반환."""
        mock_spreadsheet["fees"].get_all_records.return_value = _rows(
            ("A", "2026-Q1"), ("B", "2026-Q3"), ("C", "2026-Q1"), ("D", "2025-Q4")
        )
        assert get_fee_quarters() == ["2026-Q3", "2026-Q1", "2025-Q4"]

    def test_empty(self, mock_spreadsheet):
        assert get_fee_quarters() == []


# --- 등록 ---


class TestBatchAddFeeRecords:
    def test_appends_once(self, mock_spreadsheet):
        """append_rows 1회로 일괄 등록."""
        added = batch_add_fee_records(["홍길동", "김철수"], "2026-Q3")
        assert added == ["홍길동", "김철수"]
        mock_spreadsheet["fees"].append_rows.assert_called_once()
        rows = mock_spreadsheet["fees"].append_rows.call_args[0][0]
        assert [r[0] for r in rows] == ["홍길동", "김철수"]
        assert all(r[1] == "2026-Q3" for r in rows)
        assert all(r[2] for r in rows)  # Paid_At 타임스탬프가 채워진다

    def test_skips_existing(self, mock_spreadsheet):
        """이미 기록이 있는 회원은 건너뛴다."""
        mock_spreadsheet["fees"].get_all_records.return_value = _rows(
            ("홍길동", "2026-Q3")
        )
        added = batch_add_fee_records(["홍길동", "김철수"], "2026-Q3")
        assert added == ["김철수"]
        rows = mock_spreadsheet["fees"].append_rows.call_args[0][0]
        assert [r[0] for r in rows] == ["김철수"]

    def test_other_quarter_is_not_existing(self, mock_spreadsheet):
        """다른 분기 기록은 중복으로 치지 않는다."""
        mock_spreadsheet["fees"].get_all_records.return_value = _rows(
            ("홍길동", "2026-Q2")
        )
        assert batch_add_fee_records(["홍길동"], "2026-Q3") == ["홍길동"]

    def test_dedupes_input(self, mock_spreadsheet):
        """같은 이름이 두 번 들어와도 한 행만 만든다."""
        added = batch_add_fee_records(["홍길동", "홍길동"], "2026-Q3")
        assert added == ["홍길동"]

    def test_all_existing_writes_nothing(self, mock_spreadsheet):
        mock_spreadsheet["fees"].get_all_records.return_value = _rows(
            ("홍길동", "2026-Q3")
        )
        assert batch_add_fee_records(["홍길동"], "2026-Q3") == []
        mock_spreadsheet["fees"].append_rows.assert_not_called()

    def test_empty_input(self, mock_spreadsheet):
        assert batch_add_fee_records([], "2026-Q3") == []
        mock_spreadsheet["fees"].append_rows.assert_not_called()

    def test_clears_member_cache(self, mock_spreadsheet):
        """fee_paid가 파생값이므로 회원 캐시도 비워야 한다."""
        get_all_members.clear = MagicMock()
        batch_add_fee_records(["홍길동"], "2026-Q3")
        get_all_members.clear.assert_called()


# --- 해제 ---


class TestBatchRemoveFeeRecords:
    def test_deletes_matching_rows(self, mock_spreadsheet):
        mock_spreadsheet["fees"].get_all_records.return_value = _rows(
            ("홍길동", "2026-Q3"), ("김철수", "2026-Q3"), ("이영희", "2026-Q3")
        )
        count = batch_remove_fee_records(["홍길동", "이영희"], "2026-Q3")
        assert count == 2
        # 행 2와 행 4 — 비연속이라 역순으로 두 번 호출된다
        calls = mock_spreadsheet["fees"].delete_rows.call_args_list
        assert [c[0] for c in calls] == [(4, 4), (2, 2)]

    def test_removes_all_duplicate_rows(self, mock_spreadsheet):
        """중복 행이 있어도 전부 지워야 확실히 미납이 된다."""
        mock_spreadsheet["fees"].get_all_records.return_value = _rows(
            ("홍길동", "2026-Q3"), ("홍길동", "2026-Q3")
        )
        assert batch_remove_fee_records(["홍길동"], "2026-Q3") == 2

    def test_ignores_other_quarters(self, mock_spreadsheet):
        mock_spreadsheet["fees"].get_all_records.return_value = _rows(
            ("홍길동", "2026-Q2")
        )
        assert batch_remove_fee_records(["홍길동"], "2026-Q3") == 0
        mock_spreadsheet["fees"].delete_rows.assert_not_called()

    def test_empty_input(self, mock_spreadsheet):
        assert batch_remove_fee_records([], "2026-Q3") == 0
        mock_spreadsheet["fees"].delete_rows.assert_not_called()

    def test_clears_member_cache(self, mock_spreadsheet):
        mock_spreadsheet["fees"].get_all_records.return_value = _rows(
            ("홍길동", "2026-Q3")
        )
        get_all_members.clear = MagicMock()
        batch_remove_fee_records(["홍길동"], "2026-Q3")
        get_all_members.clear.assert_called()


class TestSetFeePaid:
    def test_register(self, mock_spreadsheet):
        assert set_fee_paid("홍길동", "2026-Q3", True) is True
        mock_spreadsheet["fees"].append_rows.assert_called_once()

    def test_register_when_already_paid(self, mock_spreadsheet):
        """이미 납부 상태면 False(변경 없음)를 반환하고 아무것도 쓰지 않는다."""
        mock_spreadsheet["fees"].get_all_records.return_value = _rows(
            ("홍길동", "2026-Q3")
        )
        assert set_fee_paid("홍길동", "2026-Q3", True) is False
        mock_spreadsheet["fees"].append_rows.assert_not_called()

    def test_unregister(self, mock_spreadsheet):
        mock_spreadsheet["fees"].get_all_records.return_value = _rows(
            ("홍길동", "2026-Q3")
        )
        assert set_fee_paid("홍길동", "2026-Q3", False) is True
        mock_spreadsheet["fees"].delete_rows.assert_called_once_with(2, 2)

    def test_unregister_when_already_unpaid(self, mock_spreadsheet):
        assert set_fee_paid("홍길동", "2026-Q3", False) is False
        mock_spreadsheet["fees"].delete_rows.assert_not_called()


# --- 분기별 일괄 삭제 ---


class TestDeleteFeeRecordsByQuarter:
    def test_groups_contiguous_runs(self, mock_spreadsheet):
        """같은 분기 행이 연속이면 delete_rows 1회로 끝난다."""
        mock_spreadsheet["fees"].get_all_records.return_value = _rows(
            ("A", "2026-Q3"), ("B", "2026-Q3"), ("C", "2026-Q3")
        )
        assert delete_fee_records_by_quarter("2026-Q3") == 3
        mock_spreadsheet["fees"].delete_rows.assert_called_once_with(2, 4)

    def test_leaves_other_quarters_untouched(self, mock_spreadsheet):
        mock_spreadsheet["fees"].get_all_records.return_value = _rows(
            ("A", "2026-Q3"), ("B", "2026-Q2"), ("C", "2026-Q3")
        )
        assert delete_fee_records_by_quarter("2026-Q3") == 2
        calls = mock_spreadsheet["fees"].delete_rows.call_args_list
        assert [c[0] for c in calls] == [(4, 4), (2, 2)]

    def test_no_records(self, mock_spreadsheet):
        assert delete_fee_records_by_quarter("2026-Q3") == 0
        mock_spreadsheet["fees"].delete_rows.assert_not_called()

    def test_clears_member_cache(self, mock_spreadsheet):
        mock_spreadsheet["fees"].get_all_records.return_value = _rows(
            ("A", "2026-Q3")
        )
        get_all_members.clear = MagicMock()
        delete_fee_records_by_quarter("2026-Q3")
        get_all_members.clear.assert_called()


class TestDeleteRowsInRuns:
    """_delete_rows_in_runs — 역순 삭제로 행 번호가 밀리지 않아야 한다."""

    def test_single_run(self):
        ws = MagicMock()
        _delete_rows_in_runs(ws, [2, 3, 4])
        ws.delete_rows.assert_called_once_with(2, 4)

    def test_multiple_runs_reverse_order(self):
        ws = MagicMock()
        _delete_rows_in_runs(ws, [2, 3, 7, 8, 12])
        assert [c[0] for c in ws.delete_rows.call_args_list] == [(12, 12), (7, 8), (2, 3)]

    def test_unsorted_input(self):
        ws = MagicMock()
        _delete_rows_in_runs(ws, [8, 2, 7, 3])
        assert [c[0] for c in ws.delete_rows.call_args_list] == [(7, 8), (2, 3)]

    def test_empty(self):
        ws = MagicMock()
        _delete_rows_in_runs(ws, [])
        ws.delete_rows.assert_not_called()


# --- Fee_Paid 표시용 미러 ---


class TestSyncMembersFeePaid:
    def test_updates_only_mismatched_rows(self, mock_spreadsheet):
        """어긋난 행만 batch_update 한다."""
        mock_spreadsheet["members"].get_all_records.return_value = [
            {"Name": "홍길동", "PIN": "0000", "Fee_Paid": "false"},  # 실제로는 납부
            {"Name": "김철수", "PIN": "0000", "Fee_Paid": "false"},  # 실제로도 미납
            {"Name": "이영희", "PIN": "0000", "Fee_Paid": "true"},  # 실제로는 미납
        ]
        mock_spreadsheet["fees"].get_all_records.return_value = _rows(
            ("홍길동", "2026-Q3")
        )
        assert _sync_members_fee_paid("2026-Q3") == 2
        batch_data = mock_spreadsheet["members"].batch_update.call_args[0][0]
        assert batch_data == [
            {"range": "C2", "values": [["true"]]},
            {"range": "C4", "values": [["false"]]},
        ]

    def test_no_write_when_already_in_sync(self, mock_spreadsheet):
        mock_spreadsheet["members"].get_all_records.return_value = [
            {"Name": "홍길동", "PIN": "0000", "Fee_Paid": "true"},
        ]
        mock_spreadsheet["fees"].get_all_records.return_value = _rows(
            ("홍길동", "2026-Q3")
        )
        assert _sync_members_fee_paid("2026-Q3") == 0
        mock_spreadsheet["members"].batch_update.assert_not_called()

    def test_mirror_failure_does_not_break_fee_write(self, mock_spreadsheet):
        """미러 동기화가 실패해도 회비 기록 등록은 성공으로 남는다."""
        mock_spreadsheet["members"].get_all_records.side_effect = RuntimeError("boom")
        assert batch_add_fee_records(["홍길동"], "2026-Q3") == ["홍길동"]
        mock_spreadsheet["fees"].append_rows.assert_called_once()


class TestClearFeeCache:
    def test_clears_member_cache_too(self):
        """fee_paid가 파생 필드이므로 회원 캐시도 함께 비운다."""
        get_all_members.clear = MagicMock()
        get_fee_records.clear = MagicMock()
        clear_fee_cache()
        get_all_members.clear.assert_called_once()
        get_fee_records.clear.assert_called_once()
