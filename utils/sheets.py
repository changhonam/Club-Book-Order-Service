"""Google Sheets CRUD 모듈"""

import functools
import time
import uuid
from datetime import datetime
from typing import Optional

import gspread
import streamlit as st
from google.oauth2.service_account import Credentials

from utils import ConfigRecord, MemberRecord, OrderRecord

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


# --- 재시도 데코레이터 ---


def with_retry(max_retries: int = 2, delay: float = 1.0):
    """gspread APIError 발생 시 재시도하는 데코레이터."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except gspread.exceptions.APIError as exc:
                    last_exc = exc
                    if attempt < max_retries:
                        time.sleep(delay)
            raise last_exc

        return wrapper

    return decorator


# --- 인증 ---


@st.cache_resource
def get_gspread_client() -> gspread.Client:
    """st.secrets 기반 인증된 gspread 클라이언트 반환 (캐싱됨)."""
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=SCOPES,
    )
    return gspread.authorize(creds)


def _get_spreadsheet():
    """스프레드시트 객체 반환."""
    client = get_gspread_client()
    spreadsheet_name = st.secrets["spreadsheet"]["name"]
    return client.open(spreadsheet_name)


# --- Members ---


@st.cache_data(ttl=600)
def get_all_members() -> list[MemberRecord]:
    """전체 회원 목록 반환. TTL=600초 캐싱."""
    ws = _get_spreadsheet().worksheet("Members")
    records = ws.get_all_records()
    return [
        MemberRecord(
            name=str(r.get("Name", "")),
            pin=str(r.get("PIN", "0000")).zfill(4),
            fee_paid=str(r.get("Fee_Paid", "false")).lower() == "true",
        )
        for r in records
    ]


def get_member_names() -> list[str]:
    """전체 회원 이름 목록만 반환."""
    return [m.name for m in get_all_members()]


def find_member(name: str) -> Optional[MemberRecord]:
    """회원 조회. 미등록이면 None 반환."""
    for m in get_all_members():
        if m.name == name:
            return m
    return None


@with_retry()
def add_member(name: str) -> bool:
    """회원 추가. 이미 존재하면 False 반환. PIN=0000, Fee_Paid=false."""
    if find_member(name) is not None:
        return False
    ws = _get_spreadsheet().worksheet("Members")
    ws.append_row([name, "0000", "false"], value_input_option="RAW")
    clear_member_cache()
    return True


@with_retry()
def remove_member(name: str) -> bool:
    """회원 삭제. 존재하지 않으면 False 반환. Orders 데이터는 보존."""
    ws = _get_spreadsheet().worksheet("Members")
    cell = ws.find(name, in_column=1)
    if cell is None:
        return False
    ws.delete_rows(cell.row)
    clear_member_cache()
    return True


@with_retry()
def update_member_pin(name: str, new_pin: str) -> bool:
    """회원 PIN 변경. 존재하지 않으면 False 반환."""
    ws = _get_spreadsheet().worksheet("Members")
    cell = ws.find(name, in_column=1)
    if cell is None:
        return False
    ws.update(range_name=f"B{cell.row}", values=[[new_pin]], value_input_option="RAW")
    clear_member_cache()
    return True


@with_retry()
def update_member_fee_paid(name: str, fee_paid: bool) -> bool:
    """회원 회비 납부 상태 변경. 존재하지 않으면 False 반환."""
    ws = _get_spreadsheet().worksheet("Members")
    cell = ws.find(name, in_column=1)
    if cell is None:
        return False
    ws.update_cell(cell.row, 3, "true" if fee_paid else "false")
    clear_member_cache()
    return True


@with_retry()
def reset_all_fee_paid() -> int:
    """전체 회원 회비 납부 상태를 미납으로 초기화. 변경 건수 반환."""
    ws = _get_spreadsheet().worksheet("Members")
    records = ws.get_all_records()
    count = 0
    for idx, r in enumerate(records):
        if str(r.get("Fee_Paid", "false")).lower() == "true":
            ws.update_cell(idx + 2, 3, "false")  # +2: 헤더 + 0-based
            count += 1
    clear_member_cache()
    return count


# --- Orders ---


@st.cache_data(ttl=300)
def get_orders_by_month(month: str) -> list[OrderRecord]:
    """특정 월의 전체 주문 목록. TTL=300초 캐싱."""
    ws = _get_spreadsheet().worksheet("Orders")
    records = ws.get_all_records()
    result = []
    for r in records:
        if r.get("Order_Month") == month:
            result.append(
                OrderRecord(
                    order_id=str(r["Order_ID"]),
                    order_month=str(r["Order_Month"]),
                    name=str(r["Name"]),
                    book_url=str(r["Book_URL"]),
                    title=str(r["Title"]),
                    author=str(r["Author"]),
                    price=int(r["Price"]),
                    created_at=str(r["Created_At"]),
                )
            )
    return result


def get_orders_by_member(name: str, month: str) -> list[OrderRecord]:
    """특정 회원의 특정 월 주문 목록."""
    orders = get_orders_by_month(month)
    return [o for o in orders if o.name == name]


@with_retry()
def add_order(
    name: str,
    month: str,
    book_url: str,
    title: str,
    author: str,
    price: int,
) -> OrderRecord:
    """주문 추가. order_id는 UUID4 자동 생성."""
    order_id = str(uuid.uuid4())
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ws = _get_spreadsheet().worksheet("Orders")
    ws.append_row([order_id, month, name, book_url, title, author, price, created_at])
    clear_order_cache()
    return OrderRecord(
        order_id=order_id,
        order_month=month,
        name=name,
        book_url=book_url,
        title=title,
        author=author,
        price=price,
        created_at=created_at,
    )


@with_retry()
def delete_order(order_id: str) -> bool:
    """주문 삭제. 존재하지 않으면 False 반환."""
    ws = _get_spreadsheet().worksheet("Orders")
    cell = ws.find(order_id, in_column=1)
    if cell is None:
        return False
    ws.delete_rows(cell.row)
    clear_order_cache()
    return True


@with_retry()
def delete_orders_by_month(month: str) -> int:
    """특정 월의 전체 주문 삭제. 삭제된 건수 반환."""
    ws = _get_spreadsheet().worksheet("Orders")
    records = ws.get_all_records()
    # 역순으로 삭제해야 행 번호가 밀리지 않음
    rows_to_delete = []
    for idx, r in enumerate(records):
        if r.get("Order_Month") == month:
            # +2: 헤더 1행 + 0-based index → 1-based row
            rows_to_delete.append(idx + 2)
    # 역순 삭제
    for row in sorted(rows_to_delete, reverse=True):
        ws.delete_rows(row)
    clear_order_cache()
    return len(rows_to_delete)


# --- Config ---


@st.cache_data(ttl=60)
def get_config() -> ConfigRecord:
    """서비스 설정 조회. TTL=60초 캐싱."""
    ws = _get_spreadsheet().worksheet("Config")
    records = ws.get_all_records()
    config_dict = {}
    for r in records:
        config_dict[r["Key"]] = r["Value"]
    return ConfigRecord(
        current_order_month=str(config_dict.get("current_order_month", "")),
        is_closed=str(config_dict.get("is_closed", "false")).lower() == "true",
        auto_close_datetime=(
            str(config_dict["auto_close_datetime"])
            if config_dict.get("auto_close_datetime")
            else None
        ),
    )


@with_retry()
def update_config(
    current_order_month: Optional[str] = None,
    is_closed: Optional[bool] = None,
    auto_close_datetime: Optional[str] = None,
) -> ConfigRecord:
    """설정 부분 업데이트. None인 필드는 변경하지 않음."""
    ws = _get_spreadsheet().worksheet("Config")
    records = ws.get_all_records()
    # Key -> row number 매핑 (헤더가 1행)
    key_row_map = {}
    for idx, r in enumerate(records):
        key_row_map[r["Key"]] = idx + 2  # +2: 헤더 + 0-based

    if current_order_month is not None:
        ws.update_cell(key_row_map["current_order_month"], 2, current_order_month)
    if is_closed is not None:
        ws.update_cell(key_row_map["is_closed"], 2, "true" if is_closed else "false")
    if auto_close_datetime is not None:
        ws.update_cell(key_row_map["auto_close_datetime"], 2, auto_close_datetime)

    clear_config_cache()
    return get_config()


# --- Logs ---


@with_retry()
def append_log(event_type: str, message: str) -> None:
    """이벤트 로그 기록. 캐싱 없음."""
    ws = _get_spreadsheet().worksheet("Logs")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ws.append_row([timestamp, event_type, message])


def get_recent_logs(limit: int = 50) -> list[dict]:
    """최근 로그 조회."""
    ws = _get_spreadsheet().worksheet("Logs")
    records = ws.get_all_records()
    # 역순으로 최근 limit건
    recent = records[-limit:] if len(records) > limit else records
    result = []
    for r in reversed(recent):
        result.append(
            {
                "timestamp": str(r.get("Timestamp", "")),
                "event_type": str(r.get("Event_Type", "")),
                "message": str(r.get("Message", "")),
            }
        )
    return result


# --- Cache helpers ---


def clear_member_cache() -> None:
    """Members 캐시 초기화."""
    get_all_members.clear()


def clear_order_cache() -> None:
    """Orders 캐시 초기화."""
    get_orders_by_month.clear()


def clear_config_cache() -> None:
    """Config 캐시 초기화."""
    get_config.clear()
