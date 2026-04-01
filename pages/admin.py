"""관리자 페이지 — 회원 관리, 신청 현황, 대리 신청, 정산, 내보내기."""

import io
import re
from datetime import datetime, time
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")

import pandas as pd
import streamlit as st

from utils.scraper import ScrapingError, scrape_book_info
from utils.settlement import calculate_monthly_payment
from utils.sheets import (
    add_order,
    append_log,
    batch_add_members,
    batch_update_fee_paid,
    clear_config_cache,
    clear_member_cache,
    clear_order_cache,
    delete_orders_by_month,
    find_member,
    get_all_members,
    get_all_payments_by_month,
    get_config,
    get_existing_order_months,
    get_member_names,
    get_orders_by_month,
    get_recent_logs,
    remove_member,
    reset_all_fee_paid,
    update_config,
    update_member_pin,
)

# --- 인증 가드 ---
if not st.session_state.get("logged_in", False):
    st.warning("로그인이 필요합니다.")
    st.stop()

if not st.session_state.get("is_admin", False):
    st.warning("관리자 권한이 필요합니다.")
    st.stop()

st.title("🔧 관리자 페이지")

config = get_config()

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
    ["접수 관리", "신청 현황", "회원 관리", "회비 관리", "대리 신청", "내보내기 & 로그"]
)

# =============================================================================
# 탭 1: 접수 관리
# =============================================================================
with tab1:
    st.subheader("접수 관리")

    # --- 현재 접수월 변경 ---
    st.markdown("#### 현재 접수월 변경")
    new_month = st.text_input(
        "접수월 (YYYY-MM)",
        value=config.current_order_month,
        key="admin_new_month",
    )
    if st.button("변경", key="btn_change_month"):
        if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", new_month):
            st.error("YYYY-MM 형식으로 입력해주세요 (예: 2026-04)")
        else:
            update_config(current_order_month=new_month)
            append_log("ADMIN_SET_MONTH", f"접수월 변경: {new_month}")
            st.success(f"접수월이 {new_month}로 변경되었습니다.")
            clear_config_cache()
            st.rerun()

    st.divider()

    # --- 마감 토글 ---
    st.markdown("#### 신청 마감")
    is_closed = st.toggle(
        "신청 마감",
        value=config.is_closed,
        key="admin_close_toggle",
    )
    if is_closed != config.is_closed:
        status_text = "마감" if is_closed else "오픈"
        update_config(is_closed=is_closed)
        append_log("ADMIN_CLOSE_MONTH", f"접수 상태 변경: {status_text}")
        st.success(f"접수 상태가 '{status_text}'으로 변경되었습니다.")
        st.rerun()

    st.divider()

    # --- 자동마감 예약 ---
    st.markdown("#### 자동마감 예약")
    if config.auto_close_datetime:
        st.info(f"현재 자동마감 예약: {config.auto_close_datetime}")
        if st.button("예약 해제", key="btn_cancel_auto_close"):
            update_config(auto_close_datetime="")
            append_log("ADMIN_CLOSE_MONTH", "자동마감 예약 해제")
            st.success("자동마감 예약이 해제되었습니다.")
            clear_config_cache()
            st.rerun()
    else:
        st.info("자동마감 예약이 설정되어 있지 않습니다.")

    col_date, col_time = st.columns(2)
    with col_date:
        close_date = st.date_input(
            "마감 날짜", value=datetime.now(KST).date(), key="admin_close_date"
        )
    with col_time:
        close_time = st.time_input(
            "마감 시간", value=time(18, 0), key="admin_close_time"
        )

    if st.button("자동마감 예약", key="btn_set_auto_close"):
        dt = datetime.combine(close_date, close_time)
        dt_str = dt.strftime("%Y-%m-%d %H:%M")
        update_config(auto_close_datetime=dt_str)
        append_log("ADMIN_CLOSE_MONTH", f"자동마감 예약: {dt_str}")
        st.success(f"자동마감이 {dt_str}에 예약되었습니다.")
        clear_config_cache()
        st.rerun()

# =============================================================================
# 탭 2: 신청 현황
# =============================================================================
with tab2:
    st.subheader("신청 현황")

    existing_months = get_existing_order_months()
    now = datetime.now(KST)
    window_months: set[str] = set()
    for i in range(12):
        year = now.year
        month = now.month - i
        while month <= 0:
            month += 12
            year -= 1
        window_months.add(f"{year:04d}-{month:02d}")
    months: list[str] = sorted(existing_months & window_months, reverse=True)
    if config.current_order_month and config.current_order_month not in months:
        months.insert(0, config.current_order_month)
    if config.current_order_month in months and months[0] != config.current_order_month:
        months.remove(config.current_order_month)
        months.insert(0, config.current_order_month)
    selected_month = st.selectbox(
        "조회 월",
        options=months,
        index=0,
        key="admin_view_month",
    )

    orders = get_orders_by_month(selected_month)

    if not orders:
        st.info(f"{selected_month}에 신청된 주문이 없습니다.")
    else:
        # --- 회원별 그룹핑 테이블 ---
        st.markdown("#### 회원별 요약")
        df_orders = pd.DataFrame(
            [
                {
                    "신청자": o.name,
                    "제목": o.title,
                    "저자": o.author,
                    "출판사": o.publisher,
                    "가격": o.price,
                    "신청일": o.created_at,
                }
                for o in orders
            ]
        )
        summary = (
            df_orders.groupby("신청자")
            .agg(주문수=("제목", "count"), 총액=("가격", "sum"))
            .reset_index()
        )
        payments = get_all_payments_by_month(selected_month)
        summary["입금"] = summary["신청자"].apply(
            lambda n: "완료" if payments.get(n) and payments[n].is_paid else "대기"
        )
        st.dataframe(summary, width="stretch")

        # --- 전체 주문 목록 ---
        st.markdown("#### 전체 주문 목록")
        st.dataframe(df_orders, width="stretch")

        # --- 예산 요약 ---
        st.markdown("#### 예산 요약")
        # 회원별로 정산을 계산해야 함
        members_in_orders = list({o.name for o in orders})
        total_all_price = 0
        total_all_support = 0
        total_all_payment = 0

        for member in sorted(members_in_orders):
            member_orders = [o for o in orders if o.name == member]
            member_total = sum(o.price for o in member_orders)
            settlement = calculate_monthly_payment(member_total)
            total_all_price += settlement.total_price
            total_all_support += settlement.club_support
            total_all_payment += settlement.user_payment

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("전체 총액", f"{total_all_price:,}원")
        with col2:
            st.metric("총 지원금", f"{total_all_support:,}원")
        with col3:
            st.metric("총 본인부담", f"{total_all_payment:,}원")

# =============================================================================
# 탭 3: 회원 관리
# =============================================================================
with tab3:
    st.subheader("회원 관리")

    # --- 회원 목록 ---
    st.markdown("#### 회원 목록")
    members = get_all_members()
    member_names = get_member_names()
    if members:
        df_members = pd.DataFrame(
            {
                "이름": [m.name for m in members],
                "PIN": ["****" for _ in members],
                "회비 납부": ["납부" if m.fee_paid else "미납" for m in members],
            }
        )
        st.dataframe(df_members, width="stretch")
    else:
        st.info("등록된 회원이 없습니다.")

    st.divider()

    # --- PIN 초기화 ---
    st.markdown("#### PIN 초기화")
    if member_names:
        pin_reset_member = st.selectbox(
            "PIN 초기화할 회원 선택", member_names, key="admin_pin_reset_member"
        )
        if st.button("PIN 초기화 (0000)", key="btn_reset_pin"):
            if update_member_pin(pin_reset_member, "0000"):
                append_log("PIN_RESET", f"PIN 초기화: {pin_reset_member}")
                st.success(
                    f"'{pin_reset_member}' 회원의 PIN이 0000으로 초기화되었습니다."
                )
                clear_member_cache()
                st.rerun()
            else:
                st.error("PIN 초기화에 실패했습니다.")
    else:
        st.info("등록된 회원이 없습니다.")

    st.divider()

    # --- 회원 추가 ---
    st.markdown("#### 회원 추가")
    st.caption("회원 이름을 입력하고 Enter → 리스트에 추가 → '일괄 추가' 클릭")

    if "member_pending_names" not in st.session_state:
        st.session_state.member_pending_names = []

    with st.form("member_add_form", clear_on_submit=True):
        new_member_name = st.text_input("새 회원 이름", key="admin_new_member")
        submitted = st.form_submit_button("추가")
        if submitted:
            name = new_member_name.strip()
            if not name:
                st.warning("이름을 입력해주세요.")
            elif name in get_member_names():
                st.error(f"'{name}'은(는) 이미 등록된 회원입니다.")
            elif name in st.session_state.member_pending_names:
                st.warning(f"'{name}'은(는) 이미 리스트에 있습니다.")
            else:
                st.session_state.member_pending_names.append(name)
                st.success(f"'{name}' 추가됨")

    pending = st.session_state.member_pending_names
    if pending:
        st.markdown(f"**추가 대기 리스트** ({len(pending)}명)")
        cols_per_row = 4
        for i in range(0, len(pending), cols_per_row):
            cols = st.columns(cols_per_row)
            for j, col in enumerate(cols):
                idx = i + j
                if idx < len(pending):
                    with col:
                        if st.button(
                            f"❌ {pending[idx]}",
                            key=f"member_remove_{idx}",
                        ):
                            st.session_state.member_pending_names.pop(idx)
                            st.rerun()

        if st.button("일괄 추가", key="btn_batch_add_member", type="primary"):
            names_to_add = list(st.session_state.member_pending_names)
            added = batch_add_members(names_to_add)
            if added:
                append_log(
                    "MEMBER_ADD_BATCH",
                    f"일괄 회원 추가: {', '.join(added)} ({len(added)}명)",
                )
                st.success(f"{len(added)}명의 회원이 추가되었습니다.")
            skipped = set(names_to_add) - set(added)
            if skipped:
                st.warning(f"이미 등록된 회원 건너뜀: {', '.join(skipped)}")
            st.session_state.member_pending_names = []
            clear_member_cache()
            st.rerun()

    st.divider()

    # --- 회원 삭제 ---
    st.markdown("#### 회원 삭제")
    if member_names:
        del_member = st.selectbox(
            "삭제할 회원 선택", member_names, key="admin_del_member"
        )
        st.warning(f"'{del_member}' 회원을 삭제하면 되돌릴 수 없습니다.")
        if st.button("정말 삭제하시겠습니까?", key="btn_del_member"):
            if remove_member(del_member):
                append_log("MEMBER_DELETE", f"회원 삭제: {del_member}")
                st.success(f"'{del_member}' 회원이 삭제되었습니다.")
                clear_member_cache()
                st.rerun()
            else:
                st.error("삭제에 실패했습니다.")
    else:
        st.info("삭제할 회원이 없습니다.")

# =============================================================================
# 탭 4: 회비 관리
# =============================================================================
with tab4:

    @st.fragment
    def fee_management_fragment():
        """회비 관리 프래그먼트 — 납부 처리 시 이 영역만 리런됩니다."""
        st.subheader("회비 관리")

        # --- 납부 대기 리스트 초기화 ---
        if "fee_pending_names" not in st.session_state:
            st.session_state.fee_pending_names = []

        # --- 빠른 납부 체크 (이름 추가) ---
        st.markdown("#### 빠른 납부 체크")
        st.caption("회원 이름을 입력하고 Enter → 리스트에 추가 → '일괄 납부 처리' 클릭")
        with st.form("fee_check_form", clear_on_submit=True):
            fee_member_name = st.text_input("회원 이름", key="fee_quick_name")
            submitted = st.form_submit_button("추가")
            if submitted:
                name = fee_member_name.strip()
                if not name:
                    st.warning("이름을 입력해주세요.")
                elif name not in get_member_names():
                    st.error(f"'{name}'은(는) 등록되지 않은 회원입니다.")
                elif name in st.session_state.fee_pending_names:
                    st.warning(f"'{name}'은(는) 이미 리스트에 있습니다.")
                else:
                    member = find_member(name)
                    if member and member.fee_paid:
                        st.info(f"'{name}'은(는) 이미 납부 처리된 회원입니다.")
                    else:
                        st.session_state.fee_pending_names.append(name)
                        st.success(f"'{name}' 추가됨")

        # --- 납부 대기 리스트 표시 ---
        pending = st.session_state.fee_pending_names
        if pending:
            st.markdown(f"**납부 대기 리스트** ({len(pending)}명)")
            cols_per_row = 4
            for i in range(0, len(pending), cols_per_row):
                cols = st.columns(cols_per_row)
                for j, col in enumerate(cols):
                    idx = i + j
                    if idx < len(pending):
                        with col:
                            if st.button(
                                f"❌ {pending[idx]}",
                                key=f"fee_remove_{idx}",
                            ):
                                st.session_state.fee_pending_names.pop(idx)
                                st.rerun(scope="fragment")

            if st.button("일괄 납부 처리", key="btn_batch_fee", type="primary"):
                names_to_update = list(st.session_state.fee_pending_names)
                count = batch_update_fee_paid(names_to_update)
                append_log(
                    "FEE_PAID_BATCH",
                    f"일괄 납부 처리: {', '.join(names_to_update)} ({count}명)",
                )
                st.success(f"{count}명의 회비가 납부 처리되었습니다.")
                st.session_state.fee_pending_names = []
                clear_member_cache()

        st.divider()

        # --- 납부 현황 ---
        st.markdown("#### 납부 현황")
        fee_members = get_all_members()
        if fee_members:
            paid_count = sum(1 for m in fee_members if m.fee_paid)
            unpaid_count = len(fee_members) - paid_count

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("전체 회원", f"{len(fee_members)}명")
            with col2:
                st.metric("납부", f"{paid_count}명")
            with col3:
                st.metric("미납", f"{unpaid_count}명")

            df_fee = pd.DataFrame(
                {
                    "이름": [m.name for m in fee_members],
                    "납부 상태": [
                        "납부" if m.fee_paid else "미납" for m in fee_members
                    ],
                }
            )
            st.dataframe(df_fee, width="stretch")
        else:
            st.info("등록된 회원이 없습니다.")

        st.divider()

        # --- 전체 회비 초기화 ---
        st.markdown("#### 전체 회비 초기화")
        st.warning(
            "모든 회원의 회비 납부 상태를 미납으로 초기화합니다. 이 작업은 되돌릴 수 없습니다."
        )
        if st.button("전체 회비 초기화", key="btn_reset_all_fee"):
            count = reset_all_fee_paid()
            append_log("FEE_RESET_ALL", f"전체 회비 초기화: {count}건")
            st.success(f"전체 회원 {count}명의 회비 상태가 미납으로 초기화되었습니다.")
            st.session_state.fee_pending_names = []
            clear_member_cache()
            st.rerun()

    fee_management_fragment()

# =============================================================================
# 탭 5: 대리 신청
# =============================================================================
with tab5:
    st.subheader("대리 신청")

    members_for_proxy = get_member_names()
    if not members_for_proxy:
        st.warning("등록된 회원이 없습니다. 먼저 회원을 추가해주세요.")
        st.stop()

    proxy_member = st.selectbox(
        "회원 선택", members_for_proxy, key="admin_proxy_member"
    )

    st.markdown("#### URL 기반 신청")
    book_url = st.text_input("Yes24 URL", key="admin_proxy_url")

    if "proxy_book_info" not in st.session_state:
        st.session_state.proxy_book_info = None

    if st.button("도서 조회", key="btn_proxy_scrape"):
        if not book_url.strip():
            st.warning("URL을 입력해주세요.")
        else:
            try:
                info = scrape_book_info(book_url.strip())
                st.session_state.proxy_book_info = info
            except ScrapingError as e:
                st.error(f"스크래핑 실패: {e}")
                st.session_state.proxy_book_info = None

    if st.session_state.proxy_book_info is not None:
        info = st.session_state.proxy_book_info
        st.markdown("**미리보기**")
        st.write(f"- **제목**: {info.title}")
        st.write(f"- **저자**: {info.author}")
        st.write(f"- **출판사**: {info.publisher}")
        st.write(f"- **판매가**: {info.price:,}원")
        if not info.is_available:
            st.warning(f"구매 불가: {info.unavailable_reason}")

        if st.button("대리 신청", key="btn_proxy_url_order"):
            order = add_order(
                name=proxy_member,
                month=config.current_order_month,
                book_url=info.url,
                title=info.title,
                author=info.author,
                price=info.price,
                publisher=info.publisher,
                isbn=info.isbn,
            )
            append_log(
                "ORDER_CREATE",
                f"관리자 대리 신청: {proxy_member} - {info.title}",
            )
            st.success(
                f"대리 신청 완료: {proxy_member} - {info.title} ({info.price:,}원)"
            )
            st.session_state.proxy_book_info = None
            clear_order_cache()
            st.rerun()

    st.divider()

    # --- 수동 입력 폼 ---
    st.markdown("#### 수동 입력")
    manual_title = st.text_input("제목", key="admin_manual_title")
    manual_author = st.text_input("저자", key="admin_manual_author")
    manual_publisher = st.text_input("출판사 (선택)", key="admin_manual_publisher")
    manual_price = st.number_input(
        "판매가 (원)", min_value=0, step=100, key="admin_manual_price"
    )

    if st.button("수동 등록", key="btn_proxy_manual_order"):
        if not manual_title.strip():
            st.warning("제목을 입력해주세요.")
        elif not manual_author.strip():
            st.warning("저자를 입력해주세요.")
        elif manual_price <= 0:
            st.warning("판매가를 입력해주세요.")
        else:
            order = add_order(
                name=proxy_member,
                month=config.current_order_month,
                book_url="",
                title=manual_title.strip(),
                author=manual_author.strip(),
                price=int(manual_price),
                publisher=manual_publisher.strip(),
            )
            append_log(
                "ORDER_CREATE",
                f"관리자 대리 신청: {proxy_member} - {manual_title.strip()}",
            )
            st.success(
                f"수동 등록 완료: {proxy_member} - {manual_title.strip()} ({int(manual_price):,}원)"
            )
            clear_order_cache()
            st.rerun()

# =============================================================================
# 탭 6: 내보내기 & 로그
# =============================================================================
with tab6:
    st.subheader("내보내기 & 로그")

    # --- Excel 내보내기 ---
    st.markdown("#### Excel 내보내기")
    export_month = st.text_input(
        "내보내기 월 (YYYY-MM)",
        value=config.current_order_month,
        key="admin_export_month",
    )

    if st.button("Excel 생성", key="btn_export_excel"):
        export_orders = get_orders_by_month(export_month)
        if not export_orders:
            st.warning(f"{export_month}에 신청된 주문이 없습니다.")
        else:
            members_in_export = sorted({o.name for o in export_orders})

            # --- Sheet 1: 신청 도서 리스트 ---
            order_rows = []
            for member in members_in_export:
                member_orders = [o for o in export_orders if o.name == member]
                for o in member_orders:
                    order_rows.append(
                        {
                            "신청자": o.name,
                            "제목": o.title,
                            "저자": o.author,
                            "출판사": o.publisher,
                            "가격": o.price,
                            "ISBN": o.isbn,
                            "URL": o.book_url,
                            "신청일": o.created_at,
                        }
                    )
            df_orders = pd.DataFrame(order_rows)

            # --- Sheet 2: 도서 신청 비용 (신청자별 요약) ---
            cost_rows = []
            for member in members_in_export:
                member_orders = [o for o in export_orders if o.name == member]
                member_total = sum(o.price for o in member_orders)
                settlement = calculate_monthly_payment(member_total)
                cost_rows.append(
                    {
                        "신청자": member,
                        "총 신청 금액": settlement.total_price,
                        "지원금": settlement.club_support,
                        "본인 부담금": settlement.user_payment,
                    }
                )
            df_costs = pd.DataFrame(cost_rows)

            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                df_orders.to_excel(writer, index=False, sheet_name="신청 도서 리스트")
                df_costs.to_excel(writer, index=False, sheet_name="도서 신청 비용")
            buffer.seek(0)

            st.download_button(
                "📥 Excel 다운로드",
                data=buffer,
                file_name=f"도서신청_{export_month}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

    st.divider()

    # --- 월간 데이터 삭제 ---
    st.markdown("#### 월간 데이터 삭제")
    delete_month = st.text_input(
        "삭제할 월 (YYYY-MM)",
        value=config.current_order_month,
        key="admin_delete_month",
    )
    st.warning(
        f"'{delete_month}'의 모든 주문 데이터가 삭제됩니다. 이 작업은 되돌릴 수 없습니다."
    )
    if st.button(
        f"정말 {delete_month}의 모든 데이터를 삭제하시겠습니까?",
        key="btn_bulk_delete",
    ):
        count = delete_orders_by_month(delete_month)
        append_log("ADMIN_BULK_DELETE", f"{delete_month} 전체 삭제: {count}건")
        st.success(f"{delete_month}의 주문 {count}건이 삭제되었습니다.")
        clear_order_cache()
        st.rerun()

    st.divider()

    # --- 최근 로그 ---
    st.markdown("#### 최근 로그")
    logs = get_recent_logs(50)
    if logs:
        df_logs = pd.DataFrame(logs)
        df_logs.columns = ["시간", "이벤트", "메시지"]
        st.dataframe(df_logs, width="stretch")
    else:
        st.info("로그가 없습니다.")
