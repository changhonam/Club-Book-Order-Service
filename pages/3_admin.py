"""관리자 페이지 — 회원 관리, 신청 현황, 대리 신청, 정산, 내보내기."""

import io
import re
from datetime import date, datetime, time

import pandas as pd
import streamlit as st

from utils.scraper import ScrapingError, scrape_book_info
from utils.settlement import calculate_monthly_payment, calculate_per_order_breakdown
from utils.sidebar import init_session_state, render_sidebar

from utils.sheets import (
    add_member,
    add_order,
    append_log,
    clear_config_cache,
    clear_order_cache,
    delete_orders_by_month,
    get_all_members,
    get_config,
    get_orders_by_month,
    get_recent_logs,
    remove_member,
    update_config,
)

# --- session_state 초기화 ---
init_session_state()

# --- 사이드바 ---
render_sidebar()

# --- 인증 가드 ---
if not st.session_state.get("logged_in", False):
    st.warning("로그인이 필요합니다.")
    st.stop()

if not st.session_state.get("is_admin", False):
    st.warning("관리자 권한이 필요합니다.")
    st.stop()

st.title("🔧 관리자 페이지")

config = get_config()

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["접수 관리", "신청 현황", "회원 관리", "대리 신청", "내보내기 & 로그"]
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
            "마감 날짜", value=date.today(), key="admin_close_date"
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

    selected_month = st.text_input(
        "조회 월 (YYYY-MM)",
        value=config.current_order_month,
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
        st.dataframe(summary, use_container_width=True)

        # --- 전체 주문 목록 ---
        st.markdown("#### 전체 주문 목록")
        st.dataframe(df_orders, use_container_width=True)

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
    if members:
        df_members = pd.DataFrame({"이름": members})
        st.dataframe(df_members, use_container_width=True)
    else:
        st.info("등록된 회원이 없습니다.")

    st.divider()

    # --- 회원 추가 ---
    st.markdown("#### 회원 추가")
    new_member_name = st.text_input("새 회원 이름", key="admin_new_member")
    if st.button("추가", key="btn_add_member"):
        if not new_member_name.strip():
            st.warning("이름을 입력해주세요.")
        else:
            name = new_member_name.strip()
            if add_member(name):
                append_log("MEMBER_ADD", f"회원 추가: {name}")
                st.success(f"'{name}' 회원이 추가되었습니다.")
                st.rerun()
            else:
                st.error(f"'{name}'은(는) 이미 등록된 회원입니다.")

    st.divider()

    # --- 회원 삭제 ---
    st.markdown("#### 회원 삭제")
    if members:
        del_member = st.selectbox("삭제할 회원 선택", members, key="admin_del_member")
        st.warning(f"'{del_member}' 회원을 삭제하면 되돌릴 수 없습니다.")
        if st.button("정말 삭제하시겠습니까?", key="btn_del_member"):
            if remove_member(del_member):
                append_log("MEMBER_DELETE", f"회원 삭제: {del_member}")
                st.success(f"'{del_member}' 회원이 삭제되었습니다.")
                st.rerun()
            else:
                st.error("삭제에 실패했습니다.")
    else:
        st.info("삭제할 회원이 없습니다.")

# =============================================================================
# 탭 4: 대리 신청
# =============================================================================
with tab4:
    st.subheader("대리 신청")

    members_for_proxy = get_all_members()
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
# 탭 5: 내보내기 & 로그
# =============================================================================
with tab5:
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
            # 회원별로 정산 계산
            rows = []
            members_in_export = sorted({o.name for o in export_orders})
            for member in members_in_export:
                member_orders = [o for o in export_orders if o.name == member]
                breakdown = calculate_per_order_breakdown(member_orders)
                breakdown_map = {b["order_id"]: b for b in breakdown}
                for o in member_orders:
                    bd = breakdown_map.get(o.order_id, {})
                    rows.append(
                        {
                            "신청자": o.name,
                            "제목": o.title,
                            "저자": o.author,
                            "가격": o.price,
                            "지원금": bd.get("support", 0),
                            "본인부담": bd.get("payment", 0),
                            "URL": o.book_url,
                            "신청일": o.created_at,
                        }
                    )

            df_export = pd.DataFrame(rows)
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                df_export.to_excel(writer, index=False, sheet_name="도서신청")
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
        st.dataframe(df_logs, use_container_width=True)
    else:
        st.info("로그가 없습니다.")
