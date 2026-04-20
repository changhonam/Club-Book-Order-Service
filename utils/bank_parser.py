"""하나은행 거래내역 엑셀 파싱 모듈."""

import re

import pandas as pd


def parse_hana_bank_excel(file) -> list[dict]:
    """하나은행 거래내역 엑셀(xls/xlsx)에서 입금 내역 추출.

    Returns:
        [{"depositor": str, "depositor_clean": str, "amount": int}, ...]
    """
    filename = getattr(file, "name", "")
    if filename.lower().endswith(".xls"):
        df = pd.read_excel(file, header=None, engine="xlrd")
    else:
        df = pd.read_excel(file, header=None, engine="openpyxl")

    # 헤더 행 탐지: '입금액' 또는 '거래일시'가 포함된 행
    header_row = None
    for i, row in df.iterrows():
        if any(str(v) in ("입금액", "거래일시") for v in row.values):
            header_row = i
            break

    if header_row is None:
        raise ValueError("하나은행 거래내역 형식이 아닙니다. 헤더 행을 찾을 수 없습니다.")

    df.columns = df.iloc[header_row]
    df = df.iloc[header_row + 1 :].reset_index(drop=True)

    # 관련 컬럼 찾기
    deposit_col = next((c for c in df.columns if "입금액" in str(c)), None)
    name_col = next((c for c in df.columns if "적요" in str(c)), None)

    if deposit_col is None or name_col is None:
        raise ValueError("입금액 또는 적요 컬럼을 찾을 수 없습니다.")

    results = []
    for _, row in df.iterrows():
        try:
            amount = int(float(str(row[deposit_col]).replace(",", "")))
        except (ValueError, TypeError):
            continue

        if amount <= 0:
            continue

        depositor = str(row[name_col]).strip()
        if not depositor or depositor in ("nan", " ", ""):
            continue
        # 합계 행 제외
        if re.match(r"^합\s*계$", depositor):
            continue
        # 이자 항목 제외
        if depositor.startswith("(") and "이자" in depositor:
            continue

        # "(( ))" 형식 제거: "원세령 ((신한은행-오픈뱅킹))" → "원세령"
        depositor_clean = re.sub(r"\s*\(\(.*?\)\)", "", depositor).strip()

        results.append(
            {
                "depositor": depositor,
                "depositor_clean": depositor_clean,
                "amount": amount,
            }
        )

    return results


def match_deposits_to_members(
    deposits: list[dict],
    member_names: list[str],
) -> tuple[dict[str, int], list[dict]]:
    """입금 내역을 회원 이름과 매칭 (부분 포함 매칭, 동일인 합산).

    Returns:
        matched: {member_name: total_deposited_amount}
        unmatched: 매칭되지 않은 입금 목록
    """
    matched_amounts: dict[str, int] = {}
    unmatched: list[dict] = []

    for deposit in deposits:
        clean = deposit["depositor_clean"]
        amount = deposit["amount"]

        found = next(
            (m for m in member_names if m in clean or clean in m),
            None,
        )

        if found:
            matched_amounts[found] = matched_amounts.get(found, 0) + amount
        else:
            unmatched.append(deposit)

    return matched_amounts, unmatched
