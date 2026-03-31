"""공통 사이드바 — 로그인 상태 표시 및 로그아웃."""

import streamlit as st

from utils.sheets import get_config


def init_session_state():
    """session_state 기본값 초기화."""
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    if "user_name" not in st.session_state:
        st.session_state.user_name = None
    if "is_admin" not in st.session_state:
        st.session_state.is_admin = False
    if "scraped_data" not in st.session_state:
        st.session_state.scraped_data = None
    if "fee_paid" not in st.session_state:
        st.session_state.fee_paid = False


def render_sidebar():
    """사이드바에 로그인 상태, 접수 상태, 로그아웃 버튼 렌더링."""
    with st.sidebar:
        st.title("📚 독서동호회")

        if st.session_state.logged_in:
            role = "관리자" if st.session_state.is_admin else "회원"
            st.info(f"👤 {st.session_state.user_name} ({role})")

            if not st.session_state.is_admin:
                if st.session_state.fee_paid:
                    st.caption("✅ 회비 납부")
                else:
                    st.caption("❌ 회비 미납")

            config = get_config()
            st.caption(f"📅 접수월: {config.current_order_month}")
            if config.is_closed:
                st.caption("🔒 신청 마감")
            else:
                st.caption("🔓 신청 접수 중")

            if st.button("로그아웃", width="stretch"):
                st.session_state.logged_in = False
                st.session_state.user_name = None
                st.session_state.is_admin = False
                st.session_state.scraped_data = None
                st.session_state.fee_paid = False
                st.rerun()
        else:
            st.caption("로그인이 필요합니다")
