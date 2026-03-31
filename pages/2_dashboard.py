"""회원 대시보드 — 도서 구매 신청 및 현황 조회."""

from datetime import datetime

import streamlit as st

from utils.scraper import ScrapingError, scrape_book_info
from utils.settlement import calculate_monthly_payment, calculate_per_order_breakdown
from utils.sheets import (
    add_order,
    append_log,
    clear_order_cache,
    delete_order,
    get_config,
    get_orders_by_member,
    update_member_pin,
)
from utils.sidebar import init_session_state, render_sidebar

# --- session_state 초기화 ---
init_session_state()

# --- 사이드바 ---
render_sidebar()

# --- 인증 가드 ---
if not st.session_state.logged_in:
    st.warning("로그인이 필요합니다")
    st.stop()

user_name: str = st.session_state.user_name
st.title(f"📖 {user_name}님의 대시보드")

# --- 설정 로드 ---
config = get_config()
current_month = config.current_order_month
is_closed = config.is_closed

# --- 월 선택 ---
now = datetime.now()
months: list[str] = []
for i in range(12):
    # 현재월부터 과거 11개월
    year = now.year
    month = now.month - i
    while month <= 0:
        month += 12
        year -= 1
    months.append(f"{year:04d}-{month:02d}")

# current_month가 목록에 없으면 맨 앞에 추가
if current_month and current_month not in months:
    months.insert(0, current_month)

default_index = months.index(current_month) if current_month in months else 0

selected_month = st.selectbox(
    "조회 월",
    options=months,
    index=default_index,
)

is_current_month = selected_month == current_month
can_modify = is_current_month and not is_closed and st.session_state.fee_paid

if not is_current_month:
    st.info("과거 월은 조회만 가능합니다 (신청/취소 불가)")

# --- 내 주문 조회 ---
my_orders = get_orders_by_member(user_name, selected_month)

# --- 정산 요약 ---
total_price = sum(o.price for o in my_orders)
settlement = calculate_monthly_payment(total_price)

col1, col2, col3 = st.columns(3)
col1.metric("총 신청금액", f"{settlement.total_price:,}원")
col2.metric("동호회 지원금", f"{settlement.club_support:,}원")
col3.metric("본인 부담금", f"{settlement.user_payment:,}원")

st.divider()

# --- 내 신청 목록 ---
st.subheader("내 신청 목록")

if my_orders:
    breakdown = calculate_per_order_breakdown(my_orders)
    breakdown_map = {b["order_id"]: b for b in breakdown}

    for order in my_orders:
        bd = breakdown_map[order.order_id]
        with st.container():
            c1, c2 = st.columns([4, 1])
            with c1:
                st.markdown(
                    f"**{order.title}** — {order.author}  \n"
                    f"판매가 {order.price:,}원 | "
                    f"지원금 {bd['support']:,}원 | "
                    f"본인부담 {bd['payment']:,}원 | "
                    f"신청일 {order.created_at}"
                )
            with c2:
                if can_modify:
                    if st.button("삭제", key=f"del_{order.order_id}"):
                        if delete_order(order.order_id):
                            append_log(
                                "ORDER_DELETE",
                                f"{user_name} 주문 삭제: {order.title}",
                            )
                            clear_order_cache()
                            st.rerun()
                        else:
                            st.error("삭제에 실패했습니다")
else:
    st.info("신청 내역이 없습니다")

st.divider()

# --- 도서 신청 폼 ---
st.subheader("도서 신청")

if not is_current_month:
    st.info("현재 접수월이 아닙니다")
elif is_closed:
    st.warning("신청이 마감되었습니다")
elif not st.session_state.fee_paid:
    st.warning("회비 납부 후 도서 신청이 가능합니다")
else:
    url_input = st.text_input(
        "Yes24 도서 URL", placeholder="https://www.yes24.com/Product/Goods/..."
    )

    if st.button("정보 불러오기"):
        if not url_input.strip():
            st.warning("URL을 입력해주세요")
        else:
            try:
                with st.spinner("도서 정보를 불러오는 중..."):
                    book_info = scrape_book_info(url_input.strip())
                st.session_state.scraped_data = book_info
            except ScrapingError as e:
                st.error(f"스크래핑 실패: {e}")
                st.session_state.scraped_data = None

    # 미리보기
    scraped = st.session_state.scraped_data
    if scraped is not None:
        st.info(
            f"**{scraped.title}**  \n"
            f"저자: {scraped.author}  \n"
            f"출판사: {scraped.publisher}  \n"
            f"판매가: {scraped.price:,}원"
        )

        if not scraped.is_available:
            st.warning(f"구매 불가: {scraped.unavailable_reason}")

        submit_disabled = not scraped.is_available
        if st.button("구매 신청", disabled=submit_disabled):
            add_order(
                name=user_name,
                month=current_month,
                book_url=scraped.url,
                title=scraped.title,
                author=scraped.author,
                price=scraped.price,
            )
            append_log(
                "ORDER_CREATE",
                f"{user_name} 주문 신청: {scraped.title} ({scraped.price:,}원)",
            )
            st.session_state.scraped_data = None
            st.success("신청이 완료되었습니다")
            st.rerun()

st.divider()

# --- PIN 변경 ---
with st.expander("PIN 변경"):
    new_pin = st.text_input(
        "새 PIN (숫자 4자리)", type="password", max_chars=4, key="new_pin"
    )
    confirm_pin = st.text_input(
        "새 PIN 확인", type="password", max_chars=4, key="confirm_pin"
    )

    if st.button("PIN 변경"):
        if not new_pin or not confirm_pin:
            st.warning("PIN을 입력해주세요")
        elif not new_pin.isdigit() or len(new_pin) != 4:
            st.error("PIN은 숫자 4자리여야 합니다")
        elif new_pin != confirm_pin:
            st.error("PIN이 일치하지 않습니다")
        else:
            if update_member_pin(user_name, new_pin):
                st.success("PIN이 변경되었습니다")
            else:
                st.error("PIN 변경에 실패했습니다")
