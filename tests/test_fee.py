"""회비 분기 계산 테스트"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from utils.fee import (
    format_quarter,
    month_to_quarter,
    parse_quarter,
    quarter_label,
    quarter_months,
    quarter_of,
)

KST = ZoneInfo("Asia/Seoul")


class TestMonthToQuarter:
    """month_to_quarter 테스트"""

    @pytest.mark.parametrize(
        "month,expected",
        [
            ("2026-01", "2026-Q1"),
            ("2026-02", "2026-Q1"),
            ("2026-03", "2026-Q1"),
            ("2026-04", "2026-Q2"),
            ("2026-05", "2026-Q2"),
            ("2026-06", "2026-Q2"),
            ("2026-07", "2026-Q3"),
            ("2026-08", "2026-Q3"),
            ("2026-09", "2026-Q3"),
            ("2026-10", "2026-Q4"),
            ("2026-11", "2026-Q4"),
            ("2026-12", "2026-Q4"),
        ],
    )
    def test_all_months(self, month, expected):
        """12개월 전체 매핑 (분기 경계 포함)."""
        assert month_to_quarter(month) == expected

    def test_strips_whitespace(self):
        assert month_to_quarter(" 2026-08 ") == "2026-Q3"

    @pytest.mark.parametrize(
        "bad", ["", "2026-13", "2026-00", "2026/03", "202603", "26-03", "2026-3", "abc"]
    )
    def test_invalid_raises(self, bad):
        with pytest.raises(ValueError):
            month_to_quarter(bad)


class TestParseAndFormatQuarter:
    """parse_quarter / format_quarter 테스트"""

    def test_parse(self):
        assert parse_quarter("2026-Q3") == (2026, 3)

    def test_format(self):
        assert format_quarter(2026, 3) == "2026-Q3"

    @pytest.mark.parametrize("quarter", ["2025-Q1", "2026-Q2", "2026-Q4", "2030-Q3"])
    def test_round_trip(self, quarter):
        assert format_quarter(*parse_quarter(quarter)) == quarter

    @pytest.mark.parametrize("bad", ["", "2026-Q0", "2026-Q5", "2026-3", "2026Q3", "Q3"])
    def test_parse_invalid_raises(self, bad):
        with pytest.raises(ValueError):
            parse_quarter(bad)

    @pytest.mark.parametrize("number", [0, 5, -1])
    def test_format_invalid_number_raises(self, number):
        with pytest.raises(ValueError):
            format_quarter(2026, number)


class TestQuarterOf:
    """quarter_of 테스트"""

    def test_kst_datetime(self):
        assert quarter_of(datetime(2026, 8, 16, 10, 30, tzinfo=KST)) == "2026-Q3"

    def test_quarter_boundary(self):
        """3월 31일 → Q1, 4월 1일 → Q2"""
        assert quarter_of(datetime(2026, 3, 31, 23, 59, tzinfo=KST)) == "2026-Q1"
        assert quarter_of(datetime(2026, 4, 1, 0, 0, tzinfo=KST)) == "2026-Q2"


class TestQuarterMonths:
    """quarter_months 테스트"""

    def test_q1(self):
        assert quarter_months("2026-Q1") == ["2026-01", "2026-02", "2026-03"]

    def test_q3(self):
        assert quarter_months("2026-Q3") == ["2026-07", "2026-08", "2026-09"]

    def test_q4(self):
        assert quarter_months("2026-Q4") == ["2026-10", "2026-11", "2026-12"]

    def test_round_trip_with_month_to_quarter(self):
        """분기의 모든 달은 다시 그 분기로 매핑된다."""
        for quarter in ("2026-Q1", "2026-Q2", "2026-Q3", "2026-Q4"):
            for month in quarter_months(quarter):
                assert month_to_quarter(month) == quarter


class TestQuarterLabel:
    """quarter_label 테스트"""

    def test_label(self):
        assert quarter_label("2026-Q3") == "2026년 3분기"

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            quarter_label("2026-08")


class TestQuarterOrdering:
    """분기 문자열의 사전순 = 시간순 성질

    get_fee_quarters()가 별도 비교자 없이 sorted()만으로 최신순 정렬할 수 있는 근거다.
    """

    def test_sorted_is_chronological(self):
        quarters = ["2026-Q4", "2025-Q1", "2026-Q1", "2025-Q4", "2026-Q2"]
        assert sorted(quarters) == [
            "2025-Q1",
            "2025-Q4",
            "2026-Q1",
            "2026-Q2",
            "2026-Q4",
        ]

    def test_year_boundary(self):
        """연말→연초 경계에서도 사전순이 유지된다."""
        assert sorted(["2026-Q1", "2025-Q4"]) == ["2025-Q4", "2026-Q1"]
