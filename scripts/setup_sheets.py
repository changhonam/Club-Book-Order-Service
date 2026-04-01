"""Google Sheets 초기 설정 스크립트 - 워크시트 및 헤더 자동 생성."""

import toml
import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
SECRETS_PATH = ".streamlit/secrets.toml"


def setup():
    secrets = toml.load(SECRETS_PATH)
    creds = Credentials.from_service_account_info(
        secrets["gcp_service_account"],
        scopes=SCOPES,
    )
    client = gspread.authorize(creds)
    spreadsheet_name = secrets["spreadsheet"]["name"]

    try:
        ss = client.open(spreadsheet_name)
        print(f"스프레드시트 '{spreadsheet_name}' 열기 성공")
    except gspread.SpreadsheetNotFound:
        print(f"오류: '{spreadsheet_name}' 스프레드시트를 찾을 수 없습니다.")
        print("Google Sheets에서 스프레드시트를 먼저 생성하고,")
        print("서비스 계정 이메일을 편집자로 공유해주세요.")
        return

    # 기존 시트 이름 목록
    existing = [ws.title for ws in ss.worksheets()]

    # Members 시트
    if "Members" not in existing:
        ws = ss.add_worksheet(title="Members", rows=100, cols=3)
        ws.update(range_name="A1", values=[["Name", "PIN", "Fee_Paid"]])
        print("Members 시트 생성 완료")
    else:
        ws = ss.worksheet("Members")
        headers = ws.row_values(1)
        if "PIN" not in headers:
            # 기존 시트가 1열짜리면 3열로 확장
            if ws.col_count < 3:
                ws.resize(cols=3)
            # 기존 Members 시트 마이그레이션: PIN, Fee_Paid 컬럼 추가
            ws.update(range_name="B1", values=[["PIN"]])
            ws.update(range_name="C1", values=[["Fee_Paid"]])
            names = ws.col_values(1)[1:]  # 헤더 제외
            if names:
                # 기존 회원에 기본값 일괄 설정
                pin_cells = [["0000"] for _ in names]
                fee_cells = [["false"] for _ in names]
                ws.update(
                    range_name=f"B2:B{len(names) + 1}",
                    values=pin_cells,
                    value_input_option="RAW",
                )
                ws.update(range_name=f"C2:C{len(names) + 1}", values=fee_cells)
            print(
                f"Members 시트 마이그레이션 완료 (PIN, Fee_Paid 추가, {len(names)}명)"
            )
        else:
            print("Members 시트 이미 최신 스키마")

    # Orders 시트
    # 목표 헤더 순서: Order_ID, Order_Month, Name, Book_URL, Title, Author, Publisher, ISBN, Price, Created_At
    target_headers = [
        "Order_ID",
        "Order_Month",
        "Name",
        "Book_URL",
        "Title",
        "Author",
        "Publisher",
        "ISBN",
        "Price",
        "Created_At",
    ]
    if "Orders" not in existing:
        ws = ss.add_worksheet(title="Orders", rows=1000, cols=10)
        ws.update(range_name="A1", values=[target_headers])
        print("Orders 시트 생성 완료")
    else:
        ws = ss.worksheet("Orders")
        headers = ws.row_values(1)
        if headers == target_headers:
            print("Orders 시트 이미 최신 스키마")
        else:
            # 기존 데이터를 읽어서 새 열 순서로 재배치
            all_data = ws.get_all_records()
            ws.clear()
            ws.resize(cols=10)
            ws.update(range_name="A1", values=[target_headers])
            if all_data:
                rows = []
                for r in all_data:
                    rows.append(
                        [
                            str(r.get("Order_ID", "")),
                            str(r.get("Order_Month", "")),
                            str(r.get("Name", "")),
                            str(r.get("Book_URL", "")),
                            str(r.get("Title", "")),
                            str(r.get("Author", "")),
                            str(r.get("Publisher", "")),
                            str(r.get("ISBN", "")),
                            r.get("Price", ""),
                            str(r.get("Created_At", "")),
                        ]
                    )
                ws.update(
                    range_name=f"A2:J{len(rows) + 1}",
                    values=rows,
                    value_input_option="RAW",
                )
            print(f"Orders 시트 마이그레이션 완료 (열 재배치, {len(all_data)}건)")

    # Config 시트
    if "Config" not in existing:
        ws = ss.add_worksheet(title="Config", rows=10, cols=2)
        ws.update(
            range_name="A1",
            values=[
                ["Key", "Value"],
                ["current_order_month", "2026-03"],
                ["is_closed", "false"],
                ["auto_close_datetime", ""],
            ],
        )
        print("Config 시트 생성 완료 (초기값 포함)")
    else:
        print("Config 시트 이미 존재")

    # Payments 시트
    if "Payments" not in existing:
        ws = ss.add_worksheet(title="Payments", rows=500, cols=4)
        ws.update(
            range_name="A1", values=[["Name", "Order_Month", "Is_Paid", "Paid_At"]]
        )
        print("Payments 시트 생성 완료")
    else:
        print("Payments 시트 이미 존재")

    # Logs 시트
    if "Logs" not in existing:
        ws = ss.add_worksheet(title="Logs", rows=1000, cols=3)
        ws.update(range_name="A1", values=[["Timestamp", "Event_Type", "Message"]])
        print("Logs 시트 생성 완료")
    else:
        print("Logs 시트 이미 존재")

    # 기본 'Sheet1' 시트 제거 (있으면)
    if "Sheet1" in existing:
        ss.del_worksheet(ss.worksheet("Sheet1"))
        print("기본 Sheet1 시트 삭제")

    print("\n초기 설정 완료!")


if __name__ == "__main__":
    setup()
