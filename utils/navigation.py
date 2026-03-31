"""네비게이션 페이지 목록 생성 로직."""

import streamlit as st


def build_page_list(*, logged_in: bool, is_admin: bool) -> list[st.Page]:
    """로그인/관리자 상태에 따른 페이지 목록 생성."""
    home = st.Page("pages/home.py", title="홈", icon="🏠", default=True)
    dashboard = st.Page("pages/dashboard.py", title="도서 구매 신청", icon="📖")

    if logged_in:
        login_or_profile = st.Page("pages/login.py", title="프로필", icon="👤")
    else:
        login_or_profile = st.Page("pages/login.py", title="로그인", icon="🔑")

    pages = [home, login_or_profile, dashboard]

    if is_admin:
        admin = st.Page("pages/admin.py", title="Admin", icon="🔧")
        pages.append(admin)

    return pages
