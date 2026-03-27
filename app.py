"""독서동호회 도서 구매 신청 서비스 - 메인 앱"""

from datetime import datetime

import streamlit as st

from utils.sheets import append_log, get_config, update_config
from utils.sidebar import init_session_state, render_sidebar

# --- 페이지 설정 ---
st.set_page_config(
    page_title="독서동호회 도서 구매 신청",
    page_icon="📚",
    layout="wide",
)

# --- session_state 초기화 ---
init_session_state()

# --- 자동마감 체크 (접속 시 실행) ---
config = get_config()
if config.auto_close_datetime and not config.is_closed:
    try:
        auto_close_dt = datetime.strptime(config.auto_close_datetime, "%Y-%m-%d %H:%M")
        if datetime.now() >= auto_close_dt:
            update_config(is_closed=True)
            append_log(
                "ADMIN_CLOSE_MONTH",
                f"{config.current_order_month} 자동마감 실행",
            )
    except ValueError:
        pass

# --- 사이드바 ---
render_sidebar()

# --- 메인 페이지 ---
st.title("📚 독서동호회 도서 구매 신청 서비스")

if not st.session_state.logged_in:
    st.markdown(
        """
        ### 서비스 안내
        - 📖 Yes24 도서 링크로 간편하게 구매 신청
        - 💰 동호회 지원금 자동 정산 (최대 30,000원)
        - 📊 신청 현황 및 정산 내역 조회

        👈 **왼쪽 메뉴에서 로그인 페이지로 이동하세요.**
        """
    )
else:
    user_name = st.session_state.user_name
    st.markdown(
        f"""
        ### 안녕하세요, {user_name}님! 👋

        왼쪽 메뉴에서 원하는 페이지로 이동하세요.

        - **📖 대시보드**: 도서 신청 및 현황 조회
        """
    )
    if st.session_state.is_admin:
        st.markdown("- **🔧 관리자**: 회원 관리, 신청 현황, 정산")
