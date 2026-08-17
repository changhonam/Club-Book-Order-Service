"""회비 분기 계산 모듈

회비는 분기 단위로 납부한다. 분기 문자열은 "YYYY-Qn" 형식이며,
n이 한 자리 숫자라 사전순 정렬이 곧 시간순 정렬이 된다.

streamlit/gspread에 의존하지 않는 순수 함수 모듈이다.
(scripts/setup_sheets.py가 마이그레이션 중에 그대로 재사용한다.)
"""

import re
from datetime import datetime

_MONTH_RE = re.compile(r"^(\d{4})-(\d{2})$")
_QUARTER_RE = re.compile(r"^(\d{4})-Q([1-4])$")


def format_quarter(year: int, number: int) -> str:
    """(2026, 3) → "2026-Q3".

    Raises:
        ValueError: number가 1~4가 아닐 때
    """
    if not 1 <= number <= 4:
        raise ValueError(f"분기는 1~4여야 합니다: {number}")
    return f"{year:04d}-Q{number}"


def parse_quarter(quarter: str) -> tuple[int, int]:
    """"2026-Q3" → (2026, 3).

    Raises:
        ValueError: 형식이 잘못됐을 때
    """
    match = _QUARTER_RE.match(str(quarter).strip())
    if match is None:
        raise ValueError(f"분기 형식이 잘못되었습니다: {quarter!r}")
    return int(match.group(1)), int(match.group(2))


def month_to_quarter(month: str) -> str:
    """"2026-08" → "2026-Q3".

    Raises:
        ValueError: 형식이 잘못됐거나 월이 1~12를 벗어날 때
    """
    match = _MONTH_RE.match(str(month).strip())
    if match is None:
        raise ValueError(f"월 형식이 잘못되었습니다: {month!r}")
    year, month_num = int(match.group(1)), int(match.group(2))
    if not 1 <= month_num <= 12:
        raise ValueError(f"월은 1~12여야 합니다: {month!r}")
    return format_quarter(year, (month_num - 1) // 3 + 1)


def quarter_of(dt: datetime) -> str:
    """datetime → "YYYY-Qn". 호출자가 KST datetime을 넘긴다."""
    return format_quarter(dt.year, (dt.month - 1) // 3 + 1)


def quarter_months(quarter: str) -> list[str]:
    """"2026-Q3" → ["2026-07", "2026-08", "2026-09"]."""
    year, number = parse_quarter(quarter)
    first = (number - 1) * 3 + 1
    return [f"{year:04d}-{m:02d}" for m in range(first, first + 3)]


def quarter_label(quarter: str) -> str:
    """UI 표시용. "2026-Q3" → "2026년 3분기"."""
    year, number = parse_quarter(quarter)
    return f"{year}년 {number}분기"
