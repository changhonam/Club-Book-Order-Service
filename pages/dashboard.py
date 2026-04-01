"""회원 대시보드 — 도서 구매 신청 및 현황 조회."""

from datetime import datetime
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")

import streamlit as st

from utils.scraper import ScrapingError, scrape_book_info
from utils.settlement import calculate_monthly_payment
from utils.sheets import (
    add_order,
    append_log,
    clear_order_cache,
    clear_payment_cache,
    delete_order,
    find_member,
    get_config,
    get_existing_order_months,
    get_orders_by_member,
    get_payment_status,
    set_payment_status,
)

# --- 인증 가드 ---
if not st.session_state.logged_in:
    st.warning("로그인이 필요합니다")
    st.stop()

user_name: str = st.session_state.user_name

# --- 회비 납부 상태 동기화 (로그인 후 변경 반영) ---
_member = find_member(user_name)
if _member is not None:
    st.session_state.fee_paid = _member.fee_paid
st.title(f"📖 {user_name}님의 도서 구매 신청")

# --- 설정 로드 ---
config = get_config()
current_month = config.current_order_month
is_closed = config.is_closed

# --- 월 선택 ---
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

# 12개월 윈도우 내에서 데이터가 있는 월만 필터 (최신순 정렬)
months: list[str] = sorted(existing_months & window_months, reverse=True)

# current_order_month는 항상 포함 (데이터 없어도 표시)
if current_month and current_month not in months:
    months.insert(0, current_month)

# current_month를 맨 앞으로
if current_month in months and months[0] != current_month:
    months.remove(current_month)
    months.insert(0, current_month)

selected_month = st.selectbox(
    "조회 월",
    options=months,
    index=0,
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

if settlement.user_payment > 0:
    is_paid = get_payment_status(user_name, selected_month)
    st.info(
        "도서를 모두 담으셨다면 아래 계좌로 **본인 부담금**을 입금해주세요.\n\n"
        "🏦 **하나은행 120-910310-76207 남창호**\n\n"
        "입금을 완료하셨다면 아래 **입금 완료** 버튼을 눌러주세요."
    )
    btn_color = "#28a745" if is_paid else "#dc3545"
    st.markdown(
        f"<style>"
        f"button[kind='primary'] {{"
        f"background-color: {btn_color} !important; "
        f"border-color: {btn_color} !important;"
        f"}}</style>",
        unsafe_allow_html=True,
    )
    if is_paid:
        if st.button("입금 완료 함", key="btn_payment_done", type="primary"):
            set_payment_status(user_name, selected_month, False)
            append_log(
                "PAYMENT_CANCEL",
                f"{user_name} {selected_month} 입금 완료 취소",
            )
            clear_payment_cache()
            st.rerun()
    elif st.button("입금 완료", key="btn_payment_done", type="primary"):
        set_payment_status(user_name, selected_month, True)
        append_log(
            "PAYMENT_DONE",
            f"{user_name} {selected_month} 입금 완료 처리",
        )
        clear_payment_cache()
        st.rerun()

st.divider()

# --- 내 신청 목록 ---
st.subheader("내 신청 목록")

if my_orders:
    for order in my_orders:
        with st.container():
            c1, c2 = st.columns([4, 1])
            with c1:
                publisher_text = f" | {order.publisher}" if order.publisher else ""
                st.markdown(
                    f"**{order.title}** — {order.author}{publisher_text}  \n"
                    f"판매가 {order.price:,}원 | "
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
                publisher=scraped.publisher,
                isbn=scraped.isbn,
            )
            append_log(
                "ORDER_CREATE",
                f"{user_name} 주문 신청: {scraped.title} ({scraped.price:,}원)",
            )
            st.session_state.scraped_data = None
            st.success("신청이 완료되었습니다")
            st.rerun()
