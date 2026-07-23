"""하나은행 거래내역 파싱 및 회원 매칭 테스트"""

import io

import pandas as pd
import pytest

from utils.bank_parser import match_deposits_to_members, parse_hana_bank_excel


def make_excel(rows: list[list]) -> io.BytesIO:
    """하나은행 거래내역 형식(안내 행 + 헤더 행 + 데이터)의 엑셀을 메모리에 생성.

    rows: [적요, 출금액, 입금액] 순서의 데이터 행 목록
    """
    data = [
        ["거래내역조회", None, None, None],
        [None, None, None, None],
        ["거래일시", "적요", "출금액", "입금액"],
        *[["2026-07-01 10:00:00", *r] for r in rows],
    ]
    buf = io.BytesIO()
    pd.DataFrame(data).to_excel(buf, index=False, header=False, engine="openpyxl")
    buf.seek(0)
    return buf


class TestParseHanaBankExcel:
    """parse_hana_bank_excel 테스트"""

    def test_deposit_only(self):
        """입금만 있는 행: 출금액 0, 순입금액 = 입금액"""
        result = parse_hana_bank_excel(make_excel([["홍길동", None, 30000]]))

        assert len(result) == 1
        assert result[0]["depositor_clean"] == "홍길동"
        assert result[0]["deposit"] == 30000
        assert result[0]["withdrawal"] == 0
        assert result[0]["amount"] == 30000

    def test_withdrawal_only(self):
        """출금만 있는 행도 추출되며 순입금액은 음수"""
        result = parse_hana_bank_excel(make_excel([["홍길동", 5000, None]]))

        assert len(result) == 1
        assert result[0]["deposit"] == 0
        assert result[0]["withdrawal"] == 5000
        assert result[0]["amount"] == -5000

    def test_deposit_and_withdrawal_in_one_row(self):
        """한 행에 입금·출금이 모두 있으면 순입금액으로 계산"""
        result = parse_hana_bank_excel(make_excel([["홍길동", 5000, 30000]]))

        assert result[0]["amount"] == 25000

    def test_empty_row_skipped(self):
        """입금·출금이 모두 없는 행은 제외"""
        result = parse_hana_bank_excel(
            make_excel([["홍길동", None, None], ["김철수", None, 10000]])
        )

        assert len(result) == 1
        assert result[0]["depositor_clean"] == "김철수"

    def test_comma_formatted_amount(self):
        """천 단위 구분자가 포함된 금액 파싱"""
        result = parse_hana_bank_excel(make_excel([["홍길동", "1,000", "30,000"]]))

        assert result[0]["deposit"] == 30000
        assert result[0]["withdrawal"] == 1000
        assert result[0]["amount"] == 29000

    def test_sum_and_interest_rows_excluded(self):
        """합계 행과 이자 행은 제외"""
        result = parse_hana_bank_excel(
            make_excel(
                [
                    ["합계", 5000, 30000],
                    ["(이자)", None, 12],
                    ["홍길동", None, 30000],
                ]
            )
        )

        assert len(result) == 1
        assert result[0]["depositor_clean"] == "홍길동"

    def test_bank_suffix_stripped(self):
        """'(( ))' 형식의 은행 정보 제거"""
        result = parse_hana_bank_excel(
            make_excel([["원세령 ((신한은행-오픈뱅킹))", None, 30000]])
        )

        assert result[0]["depositor"] == "원세령 ((신한은행-오픈뱅킹))"
        assert result[0]["depositor_clean"] == "원세령"

    def test_missing_withdrawal_column(self):
        """출금액 컬럼이 없는 형식도 파싱 가능 (출금액 0)"""
        data = [
            ["거래일시", "적요", "입금액"],
            ["2026-07-01 10:00:00", "홍길동", 30000],
        ]
        buf = io.BytesIO()
        pd.DataFrame(data).to_excel(buf, index=False, header=False, engine="openpyxl")
        buf.seek(0)

        result = parse_hana_bank_excel(buf)

        assert result[0]["withdrawal"] == 0
        assert result[0]["amount"] == 30000

    def test_invalid_format_raises(self):
        """헤더를 찾을 수 없으면 ValueError"""
        buf = io.BytesIO()
        pd.DataFrame([["아무", "내용"]]).to_excel(
            buf, index=False, header=False, engine="openpyxl"
        )
        buf.seek(0)

        with pytest.raises(ValueError):
            parse_hana_bank_excel(buf)


class TestMatchDepositsToMembers:
    """match_deposits_to_members 테스트"""

    @staticmethod
    def tx(name: str, deposit: int = 0, withdrawal: int = 0) -> dict:
        return {
            "depositor": name,
            "depositor_clean": name,
            "deposit": deposit,
            "withdrawal": withdrawal,
            "amount": deposit - withdrawal,
        }

    def test_net_amount(self):
        """입금 후 출금이 있으면 순입금액으로 집계"""
        matched, unmatched = match_deposits_to_members(
            [self.tx("홍길동", deposit=35000), self.tx("홍길동", withdrawal=5000)],
            ["홍길동"],
        )

        assert matched["홍길동"] == {
            "deposit": 35000,
            "withdrawal": 5000,
            "net": 30000,
        }
        assert unmatched == []

    def test_multiple_deposits_summed(self):
        """동일인의 여러 입금은 합산"""
        matched, _ = match_deposits_to_members(
            [self.tx("홍길동", deposit=10000), self.tx("홍길동", deposit=20000)],
            ["홍길동"],
        )

        assert matched["홍길동"]["net"] == 30000

    def test_partial_name_match(self):
        """후보가 1명뿐이면 부분 포함 매칭 채택"""
        matched, unmatched = match_deposits_to_members(
            [self.tx("홍길동님", deposit=30000)],
            ["홍길동"],
        )

        assert matched["홍길동"]["net"] == 30000
        assert unmatched == []

    def test_exact_match_wins_over_partial(self):
        """정확 일치가 부분 일치보다 우선"""
        matched, unmatched = match_deposits_to_members(
            [self.tx("김민수", deposit=30000)],
            ["김민", "김민수"],
        )

        assert matched == {"김민수": {"deposit": 30000, "withdrawal": 0, "net": 30000}}
        assert unmatched == []

    def test_ambiguous_partial_match_not_guessed(self):
        """부분 일치 후보가 2명 이상이면 오매칭 대신 미매칭 처리"""
        matched, unmatched = match_deposits_to_members(
            [self.tx("김민수님", deposit=30000)],
            ["김민", "김민수"],
        )

        assert matched == {}
        assert len(unmatched) == 1
        assert unmatched[0]["candidates"] == ["김민", "김민수"]

    def test_ambiguous_withdrawal_not_deducted(self):
        """후보가 여러 명인 출금은 어느 회원에게도 차감하지 않음"""
        matched, unmatched = match_deposits_to_members(
            [self.tx("김민수", deposit=30000), self.tx("김민수님", withdrawal=5000)],
            ["김민", "김민수"],
        )

        assert matched["김민수"]["withdrawal"] == 0
        assert matched["김민수"]["net"] == 30000
        assert unmatched == []  # 출금만 있는 내역은 미매칭 목록에서 제외

    def test_whitespace_normalized(self):
        """적요에 공백이 섞여 있어도 매칭"""
        matched, unmatched = match_deposits_to_members(
            [self.tx("홍 길동", deposit=30000)],
            ["홍길동"],
        )

        assert matched["홍길동"]["net"] == 30000
        assert unmatched == []

    def test_empty_name_not_matched_to_sole_member(self):
        """이름 없는 적요는 회원이 1명뿐이어도 귀속하지 않음

        빈 문자열은 모든 이름의 부분 문자열이므로 가드가 없으면
        정체불명 입금이 유일한 후보에게 자동 귀속된다.
        """
        matched, unmatched = match_deposits_to_members(
            [self.tx("", deposit=30000)],
            ["홍길동"],
        )

        assert matched == {}
        assert len(unmatched) == 1
        assert unmatched[0]["candidates"] == []

    def test_empty_name_not_matched_with_many_members(self):
        """회원이 여러 명일 때도 이름 없는 적요는 후보를 만들지 않음"""
        matched, unmatched = match_deposits_to_members(
            [self.tx("", deposit=30000)],
            ["홍길동", "김철수", "이영희"],
        )

        assert matched == {}
        assert unmatched[0]["candidates"] == []

    def test_empty_member_name_ignored(self):
        """회원 명단에 빈 이름이 있어도 다른 사람의 입금을 가로채지 않음"""
        matched, unmatched = match_deposits_to_members(
            [self.tx("홍길동님", deposit=30000)],
            ["", "홍길동"],
        )

        assert matched == {"홍길동": {"deposit": 30000, "withdrawal": 0, "net": 30000}}
        assert unmatched == []

    def test_bank_info_only_deposit_end_to_end(self):
        """적요에 은행 정보만 있는 입금은 파싱~매칭 전 구간에서 미매칭 처리"""
        txs = parse_hana_bank_excel(
            make_excel([["((신한은행-오픈뱅킹))", None, 30000]])
        )
        assert txs[0]["depositor_clean"] == ""

        matched, unmatched = match_deposits_to_members(txs, ["홍길동"])

        assert matched == {}
        assert unmatched[0]["depositor"] == "((신한은행-오픈뱅킹))"

    def test_unmatched_deposit_reported(self):
        """매칭되지 않은 입금은 unmatched로 반환"""
        matched, unmatched = match_deposits_to_members(
            [self.tx("이몽룡", deposit=30000)],
            ["홍길동"],
        )

        assert matched == {}
        assert len(unmatched) == 1
        assert unmatched[0]["depositor"] == "이몽룡"
        assert unmatched[0]["candidates"] == []

    def test_unmatched_withdrawal_ignored(self):
        """회원과 무관한 출금(도서 구매 등)은 미매칭 목록에 포함하지 않음"""
        matched, unmatched = match_deposits_to_members(
            [self.tx("예스24", withdrawal=120000)],
            ["홍길동"],
        )

        assert matched == {}
        assert unmatched == []

    def test_withdrawal_exceeds_deposit(self):
        """출금이 입금보다 크면 순입금액은 음수"""
        matched, _ = match_deposits_to_members(
            [self.tx("홍길동", deposit=10000), self.tx("홍길동", withdrawal=15000)],
            ["홍길동"],
        )

        assert matched["홍길동"]["net"] == -5000
