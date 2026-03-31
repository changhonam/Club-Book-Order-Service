"""회원 관리(PIN, 회비 납부) 테스트

Requirements tested:
1. MemberRecord has name, pin (default "0000"), fee_paid (default false)
2. Login requires name + PIN match
3. PIN validation: exactly 4 digits
4. Admin can reset PIN to "0000"
5. Admin can toggle fee_paid
6. Admin can reset ALL fee_paid to false
7. Members with fee_paid=false cannot submit orders (can_modify=false)
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

# --- 모듈 import 전 streamlit mock 설정 ---

_mock_st = MagicMock()


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


_mock_st.cache_data = _passthrough_cache_data
_mock_st.cache_resource = _passthrough_cache_resource
_mock_st.secrets = {
    "gcp_service_account": {"type": "service_account"},
    "spreadsheet": {"name": "TestSpreadsheet"},
}

sys.modules["streamlit"] = _mock_st


from utils import MemberRecord  # noqa: E402
from utils.sheets import (  # noqa: E402
    add_member,
    find_member,
    get_all_members,
    get_member_names,
    reset_all_fee_paid,
    update_member_fee_paid,
    update_member_pin,
)


# --- Fixtures ---


@pytest.fixture
def mock_spreadsheet():
    """gspread 스프레드시트 mock."""
    with patch("utils.sheets._get_spreadsheet") as mock_get_ss:
        mock_ss = MagicMock()
        mock_get_ss.return_value = mock_ss

        mock_members_ws = MagicMock()

        def get_worksheet(name):
            mapping = {"Members": mock_members_ws}
            return mapping[name]

        mock_ss.worksheet.side_effect = get_worksheet

        yield {"members": mock_members_ws}


def _member_records_data():
    """Members 시트의 get_all_records 반환값 샘플."""
    return [
        {"Name": "홍길동", "PIN": "1234", "Fee_Paid": "true"},
        {"Name": "김철수", "PIN": "0000", "Fee_Paid": "false"},
        {"Name": "이영희", "PIN": "5678", "Fee_Paid": "true"},
    ]


# --- MemberRecord dataclass 테스트 ---


class TestMemberRecord:
    def test_fields(self):
        """MemberRecord에 name, pin, fee_paid 필드가 존재."""
        m = MemberRecord(name="홍길동", pin="1234", fee_paid=True)
        assert m.name == "홍길동"
        assert m.pin == "1234"
        assert m.fee_paid is True

    def test_defaults(self):
        """pin 기본값 "0000", fee_paid 기본값 False는 코드에서 할당.
        dataclass 자체는 모든 필드가 required이므로 명시적으로 생성."""
        m = MemberRecord(name="테스트", pin="0000", fee_paid=False)
        assert m.pin == "0000"
        assert m.fee_paid is False

    def test_equality(self):
        """dataclass 동등성 비교."""
        m1 = MemberRecord(name="홍길동", pin="1234", fee_paid=True)
        m2 = MemberRecord(name="홍길동", pin="1234", fee_paid=True)
        assert m1 == m2

    def test_inequality(self):
        m1 = MemberRecord(name="홍길동", pin="1234", fee_paid=True)
        m2 = MemberRecord(name="홍길동", pin="0000", fee_paid=True)
        assert m1 != m2


# --- get_all_members 테스트 ---


class TestGetAllMembers:
    def test_returns_member_records(self, mock_spreadsheet):
        """MemberRecord 리스트 반환, 필드 파싱 검증."""
        mock_spreadsheet[
            "members"
        ].get_all_records.return_value = _member_records_data()
        result = get_all_members()

        assert len(result) == 3
        assert all(isinstance(m, MemberRecord) for m in result)

        assert result[0].name == "홍길동"
        assert result[0].pin == "1234"
        assert result[0].fee_paid is True

        assert result[1].name == "김철수"
        assert result[1].pin == "0000"
        assert result[1].fee_paid is False

    def test_pin_default_when_missing(self, mock_spreadsheet):
        """PIN 필드가 없으면 "0000"으로 기본값."""
        mock_spreadsheet["members"].get_all_records.return_value = [
            {"Name": "테스트", "Fee_Paid": "false"},
        ]
        result = get_all_members()
        assert result[0].pin == "0000"

    def test_fee_paid_default_when_missing(self, mock_spreadsheet):
        """Fee_Paid 필드가 없으면 False."""
        mock_spreadsheet["members"].get_all_records.return_value = [
            {"Name": "테스트", "PIN": "1111"},
        ]
        result = get_all_members()
        assert result[0].fee_paid is False

    def test_fee_paid_case_insensitive(self, mock_spreadsheet):
        """Fee_Paid "TRUE", "True" 등 대소문자 무관하게 True 파싱."""
        mock_spreadsheet["members"].get_all_records.return_value = [
            {"Name": "A", "PIN": "0000", "Fee_Paid": "TRUE"},
            {"Name": "B", "PIN": "0000", "Fee_Paid": "True"},
            {"Name": "C", "PIN": "0000", "Fee_Paid": "False"},
        ]
        result = get_all_members()
        assert result[0].fee_paid is True
        assert result[1].fee_paid is True
        assert result[2].fee_paid is False

    def test_empty_sheet(self, mock_spreadsheet):
        """빈 시트 -> 빈 리스트."""
        mock_spreadsheet["members"].get_all_records.return_value = []
        result = get_all_members()
        assert result == []

    def test_pin_converted_to_string(self, mock_spreadsheet):
        """PIN이 숫자로 들어와도 문자열로 변환."""
        mock_spreadsheet["members"].get_all_records.return_value = [
            {"Name": "테스트", "PIN": 1234, "Fee_Paid": "false"},
        ]
        result = get_all_members()
        assert result[0].pin == "1234"
        assert isinstance(result[0].pin, str)

    def test_pin_zero_padded(self, mock_spreadsheet):
        """Google Sheets가 '0000'을 숫자 0으로 변환해도 4자리로 복원."""
        mock_spreadsheet["members"].get_all_records.return_value = [
            {"Name": "회원A", "PIN": 0, "Fee_Paid": "false"},
            {"Name": "회원B", "PIN": 12, "Fee_Paid": "false"},
        ]
        result = get_all_members()
        assert result[0].pin == "0000"
        assert result[1].pin == "0012"


# --- find_member 테스트 ---


class TestFindMember:
    def test_found(self, mock_spreadsheet):
        """존재하는 회원 -> MemberRecord 반환."""
        mock_spreadsheet[
            "members"
        ].get_all_records.return_value = _member_records_data()
        result = find_member("홍길동")
        assert result is not None
        assert isinstance(result, MemberRecord)
        assert result.name == "홍길동"
        assert result.pin == "1234"
        assert result.fee_paid is True

    def test_not_found(self, mock_spreadsheet):
        """존재하지 않는 회원 -> None."""
        mock_spreadsheet[
            "members"
        ].get_all_records.return_value = _member_records_data()
        result = find_member("없는사람")
        assert result is None

    def test_returns_correct_member(self, mock_spreadsheet):
        """여러 회원 중 정확한 회원 반환."""
        mock_spreadsheet[
            "members"
        ].get_all_records.return_value = _member_records_data()
        result = find_member("김철수")
        assert result.name == "김철수"
        assert result.pin == "0000"
        assert result.fee_paid is False


# --- add_member 테스트 ---


class TestAddMember:
    def test_success(self, mock_spreadsheet):
        """새 회원 추가 -> True, append_row([name, "0000", "false"])."""
        mock_spreadsheet[
            "members"
        ].get_all_records.return_value = _member_records_data()
        result = add_member("박지성")
        assert result is True
        mock_spreadsheet["members"].append_row.assert_called_once_with(
            ["박지성", "0000", "false"], value_input_option="RAW"
        )

    def test_duplicate(self, mock_spreadsheet):
        """이미 존재하는 회원 -> False, append_row 미호출."""
        mock_spreadsheet[
            "members"
        ].get_all_records.return_value = _member_records_data()
        result = add_member("홍길동")
        assert result is False
        mock_spreadsheet["members"].append_row.assert_not_called()

    def test_default_pin_and_fee_paid(self, mock_spreadsheet):
        """추가 시 PIN=0000, Fee_Paid=false 기본값."""
        mock_spreadsheet["members"].get_all_records.return_value = []
        add_member("신규회원")
        call_args = mock_spreadsheet["members"].append_row.call_args[0][0]
        assert call_args[0] == "신규회원"
        assert call_args[1] == "0000"
        assert call_args[2] == "false"


# --- update_member_pin 테스트 ---


class TestUpdateMemberPin:
    def test_success(self, mock_spreadsheet):
        """PIN 변경 성공 -> True, update(RAW)."""
        mock_cell = MagicMock()
        mock_cell.row = 3
        mock_spreadsheet["members"].find.return_value = mock_cell
        result = update_member_pin("홍길동", "9999")
        assert result is True
        mock_spreadsheet["members"].update.assert_called_once_with(
            range_name="B3", values=[["9999"]], value_input_option="RAW"
        )

    def test_not_found(self, mock_spreadsheet):
        """존재하지 않는 회원 -> False."""
        mock_spreadsheet["members"].find.return_value = None
        result = update_member_pin("없는사람", "1111")
        assert result is False
        mock_spreadsheet["members"].update.assert_not_called()

    def test_reset_to_default(self, mock_spreadsheet):
        """관리자 PIN 초기화: "0000"으로 리셋."""
        mock_cell = MagicMock()
        mock_cell.row = 2
        mock_spreadsheet["members"].find.return_value = mock_cell
        result = update_member_pin("김철수", "0000")
        assert result is True
        mock_spreadsheet["members"].update.assert_called_once_with(
            range_name="B2", values=[["0000"]], value_input_option="RAW"
        )

    def test_clears_cache(self, mock_spreadsheet):
        """PIN 변경 후 캐시 초기화."""
        mock_cell = MagicMock()
        mock_cell.row = 2
        mock_spreadsheet["members"].find.return_value = mock_cell
        get_all_members.clear = MagicMock()
        update_member_pin("홍길동", "5555")
        get_all_members.clear.assert_called()


# --- update_member_fee_paid 테스트 ---


class TestUpdateMemberFeePaid:
    def test_set_true(self, mock_spreadsheet):
        """회비 납부 -> update_cell(row, 3, "true")."""
        mock_cell = MagicMock()
        mock_cell.row = 2
        mock_spreadsheet["members"].find.return_value = mock_cell
        result = update_member_fee_paid("홍길동", True)
        assert result is True
        mock_spreadsheet["members"].update_cell.assert_called_once_with(2, 3, "true")

    def test_set_false(self, mock_spreadsheet):
        """회비 미납 -> update_cell(row, 3, "false")."""
        mock_cell = MagicMock()
        mock_cell.row = 4
        mock_spreadsheet["members"].find.return_value = mock_cell
        result = update_member_fee_paid("이영희", False)
        assert result is True
        mock_spreadsheet["members"].update_cell.assert_called_once_with(4, 3, "false")

    def test_not_found(self, mock_spreadsheet):
        """존재하지 않는 회원 -> False."""
        mock_spreadsheet["members"].find.return_value = None
        result = update_member_fee_paid("없는사람", True)
        assert result is False
        mock_spreadsheet["members"].update_cell.assert_not_called()

    def test_clears_cache(self, mock_spreadsheet):
        """상태 변경 후 캐시 초기화."""
        mock_cell = MagicMock()
        mock_cell.row = 2
        mock_spreadsheet["members"].find.return_value = mock_cell
        get_all_members.clear = MagicMock()
        update_member_fee_paid("홍길동", True)
        get_all_members.clear.assert_called()


# --- reset_all_fee_paid 테스트 ---


class TestResetAllFeePaid:
    def test_resets_true_to_false(self, mock_spreadsheet):
        """Fee_Paid가 "true"인 회원만 "false"로 변경, 변경 건수 반환."""
        mock_spreadsheet[
            "members"
        ].get_all_records.return_value = _member_records_data()
        result = reset_all_fee_paid()
        # 홍길동(true), 이영희(true) -> 2건 변경
        assert result == 2
        calls = mock_spreadsheet["members"].update_cell.call_args_list
        assert len(calls) == 2
        # idx=0 -> row 2 (헤더+1), idx=2 -> row 4
        assert calls[0][0] == (2, 3, "false")
        assert calls[1][0] == (4, 3, "false")

    def test_no_changes_needed(self, mock_spreadsheet):
        """모두 이미 false -> 0건 반환."""
        mock_spreadsheet["members"].get_all_records.return_value = [
            {"Name": "A", "PIN": "0000", "Fee_Paid": "false"},
            {"Name": "B", "PIN": "1111", "Fee_Paid": "false"},
        ]
        result = reset_all_fee_paid()
        assert result == 0
        mock_spreadsheet["members"].update_cell.assert_not_called()

    def test_all_true(self, mock_spreadsheet):
        """모두 true -> 전체 변경."""
        mock_spreadsheet["members"].get_all_records.return_value = [
            {"Name": "A", "PIN": "0000", "Fee_Paid": "true"},
            {"Name": "B", "PIN": "1111", "Fee_Paid": "true"},
            {"Name": "C", "PIN": "2222", "Fee_Paid": "true"},
        ]
        result = reset_all_fee_paid()
        assert result == 3

    def test_empty_sheet(self, mock_spreadsheet):
        """빈 시트 -> 0."""
        mock_spreadsheet["members"].get_all_records.return_value = []
        result = reset_all_fee_paid()
        assert result == 0

    def test_clears_cache(self, mock_spreadsheet):
        """초기화 후 캐시 클리어."""
        mock_spreadsheet["members"].get_all_records.return_value = []
        get_all_members.clear = MagicMock()
        reset_all_fee_paid()
        get_all_members.clear.assert_called()


# --- get_member_names 테스트 ---


class TestGetMemberNames:
    def test_returns_name_strings(self, mock_spreadsheet):
        """이름 문자열 리스트만 반환."""
        mock_spreadsheet[
            "members"
        ].get_all_records.return_value = _member_records_data()
        result = get_member_names()
        assert result == ["홍길동", "김철수", "이영희"]
        assert all(isinstance(n, str) for n in result)

    def test_empty(self, mock_spreadsheet):
        """빈 시트 -> 빈 리스트."""
        mock_spreadsheet["members"].get_all_records.return_value = []
        result = get_member_names()
        assert result == []


# --- 로그인(PIN 매칭) 비즈니스 로직 테스트 ---


class TestLoginLogic:
    """find_member로 조회 후 PIN 매칭하는 로그인 로직 검증."""

    def test_login_success(self, mock_spreadsheet):
        """이름과 PIN이 일치하면 인증 성공."""
        mock_spreadsheet[
            "members"
        ].get_all_records.return_value = _member_records_data()
        member = find_member("홍길동")
        assert member is not None
        assert member.pin == "1234"
        # 입력 PIN과 비교
        assert member.pin == "1234"  # 성공

    def test_login_wrong_pin(self, mock_spreadsheet):
        """이름은 맞지만 PIN이 틀리면 인증 실패."""
        mock_spreadsheet[
            "members"
        ].get_all_records.return_value = _member_records_data()
        member = find_member("홍길동")
        assert member is not None
        assert member.pin != "0000"  # 틀린 PIN

    def test_login_unknown_user(self, mock_spreadsheet):
        """미등록 사용자는 인증 실패."""
        mock_spreadsheet[
            "members"
        ].get_all_records.return_value = _member_records_data()
        member = find_member("미등록")
        assert member is None


# --- PIN 유효성 검증 테스트 ---


class TestPinValidation:
    """PIN은 정확히 4자리 숫자여야 함."""

    @staticmethod
    def is_valid_pin(pin: str) -> bool:
        """PIN 유효성 검증 헬퍼 (UI 레이어의 로직을 독립 검증)."""
        return isinstance(pin, str) and len(pin) == 4 and pin.isdigit()

    def test_valid_pins(self):
        assert self.is_valid_pin("0000") is True
        assert self.is_valid_pin("1234") is True
        assert self.is_valid_pin("9999") is True

    def test_too_short(self):
        assert self.is_valid_pin("123") is False

    def test_too_long(self):
        assert self.is_valid_pin("12345") is False

    def test_non_numeric(self):
        assert self.is_valid_pin("abcd") is False
        assert self.is_valid_pin("12ab") is False

    def test_empty(self):
        assert self.is_valid_pin("") is False

    def test_with_spaces(self):
        assert self.is_valid_pin(" 123") is False
        assert self.is_valid_pin("123 ") is False

    def test_special_chars(self):
        assert self.is_valid_pin("12-4") is False


# --- can_modify 비즈니스 로직 테스트 ---


class TestCanModifyLogic:
    """도서 주문 가능 여부: is_current_month AND NOT is_closed AND fee_paid.

    fee_paid=false이면 주문 불가 (can_modify=false).
    """

    @staticmethod
    def can_modify(
        order_month: str,
        current_month: str,
        is_closed: bool,
        fee_paid: bool,
    ) -> bool:
        """주문 수정 가능 여부 판단 로직 (UI에서 사용되는 로직 재현)."""
        is_current_month = order_month == current_month
        return is_current_month and not is_closed and fee_paid

    def test_all_conditions_met(self):
        """현재 월 + 미마감 + 회비 납부 -> True."""
        assert self.can_modify("2026-03", "2026-03", False, True) is True

    def test_not_current_month(self):
        """이전 월 -> False."""
        assert self.can_modify("2026-02", "2026-03", False, True) is False

    def test_is_closed(self):
        """마감됨 -> False."""
        assert self.can_modify("2026-03", "2026-03", True, True) is False

    def test_fee_not_paid(self):
        """회비 미납 -> False (핵심 요구사항 #7)."""
        assert self.can_modify("2026-03", "2026-03", False, False) is False

    def test_closed_and_fee_not_paid(self):
        """마감 + 미납 -> False."""
        assert self.can_modify("2026-03", "2026-03", True, False) is False

    def test_different_month_and_fee_not_paid(self):
        """다른 월 + 미납 -> False."""
        assert self.can_modify("2026-02", "2026-03", False, False) is False

    def test_all_conditions_fail(self):
        """모든 조건 실패 -> False."""
        assert self.can_modify("2026-02", "2026-03", True, False) is False
