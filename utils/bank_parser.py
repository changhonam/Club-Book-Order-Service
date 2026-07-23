"""하나은행 거래내역 엑셀 파싱 모듈."""

import re

import pandas as pd


def _parse_amount(value) -> int:
    """금액 셀을 정수로 변환 (변환 불가하거나 음수면 0)."""
    try:
        amount = int(float(str(value).replace(",", "")))
    except (ValueError, TypeError):
        return 0
    return amount if amount > 0 else 0


def parse_hana_bank_excel(file) -> list[dict]:
    """하나은행 거래내역 엑셀(xls/xlsx)에서 거래 내역 추출.

    Returns:
        [{"depositor": str, "depositor_clean": str,
          "deposit": int, "withdrawal": int, "amount": int}, ...]
        amount는 순입금액(입금액 - 출금액)
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
        raise ValueError(
            "하나은행 거래내역 형식이 아닙니다. 헤더 행을 찾을 수 없습니다."
        )

    df.columns = df.iloc[header_row]
    df = df.iloc[header_row + 1 :].reset_index(drop=True)

    # 관련 컬럼 찾기
    deposit_col = next((c for c in df.columns if "입금액" in str(c)), None)
    withdrawal_col = next((c for c in df.columns if "출금액" in str(c)), None)
    name_col = next((c for c in df.columns if "적요" in str(c)), None)

    if deposit_col is None or name_col is None:
        raise ValueError("입금액 또는 적요 컬럼을 찾을 수 없습니다.")

    results = []
    for _, row in df.iterrows():
        deposit = _parse_amount(row[deposit_col])
        withdrawal = (
            _parse_amount(row[withdrawal_col]) if withdrawal_col is not None else 0
        )

        if deposit == 0 and withdrawal == 0:
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
                "deposit": deposit,
                "withdrawal": withdrawal,
                "amount": deposit - withdrawal,
            }
        )

    return results


def _normalize_name(name: str) -> str:
    """이름 비교용 정규화: 모든 공백 제거 ('홍 길동' → '홍길동')."""
    return re.sub(r"\s+", "", name)


def match_deposits_to_members(
    transactions: list[dict],
    member_names: list[str],
) -> tuple[dict[str, dict], list[dict]]:
    """거래 내역을 회원 이름과 매칭 (동일인 합산).

    정확히 일치하는 회원을 우선 찾고, 없으면 부분 포함 매칭으로 넘어간다.
    어느 단계든 후보가 2명 이상이면 오매칭 대신 미매칭으로 처리한다.
    (예: 회원 '김민'과 '김민수'가 함께 있을 때 적요 '김민수님')

    Returns:
        matched: {member_name: {"deposit": int, "withdrawal": int, "net": int}}
                 net은 순입금액(입금액 합계 - 출금액 합계)
        unmatched: 매칭되지 않은 입금 목록 (출금만 있는 내역은 회비와 무관하므로 제외)
                   후보가 여러 명이라 보류된 경우 "candidates" 키에 후보명이 담긴다
    """
    matched: dict[str, dict] = {}
    unmatched: list[dict] = []
    normalized_members = [(m, _normalize_name(m)) for m in member_names]

    for tx in transactions:
        clean = _normalize_name(tx["depositor_clean"])

        # 정확 일치 우선, 없으면 부분 포함 매칭
        candidates = [m for m, n in normalized_members if n == clean]
        if not candidates:
            candidates = [m for m, n in normalized_members if n in clean or clean in n]

        found = candidates[0] if len(candidates) == 1 else None

        if found:
            entry = matched.setdefault(found, {"deposit": 0, "withdrawal": 0, "net": 0})
            entry["deposit"] += tx["deposit"]
            entry["withdrawal"] += tx["withdrawal"]
            entry["net"] = entry["deposit"] - entry["withdrawal"]
        elif tx["deposit"] > 0:
            unmatched.append({**tx, "candidates": candidates})

    return matched, unmatched
