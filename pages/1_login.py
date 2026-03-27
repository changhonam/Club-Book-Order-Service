"""로그인 페이지 — 이름 기반 심플 로그인 + 관리자 비밀번호 인증."""

import streamlit as st

from utils.sheets import append_log, find_member
from utils.sidebar import init_session_state, render_sidebar

# --- session_state 초기화 ---
init_session_state()

# --- 사이드바 ---
render_sidebar()

# 관리자 인증 중간 단계 플래그
if "_pending_admin" not in st.session_state:
    st.session_state._pending_admin = False
if "_pending_name" not in st.session_state:
    st.session_state._pending_name = None

st.title("📚 독서동호회 도서 구매 신청")
st.subheader("로그인")

# --- 이미 로그인 상태 ---
if st.session_state.logged_in:
    role = "관리자" if st.session_state.is_admin else "회원"
    st.success(f"{st.session_state.user_name}님으로 로그인되어 있습니다 ({role})")
    if st.button("로그아웃"):
        st.session_state.logged_in = False
        st.session_state.user_name = None
        st.session_state.is_admin = False
        st.session_state._pending_admin = False
        st.session_state._pending_name = None
        st.rerun()

# --- 관리자 비밀번호 입력 단계 ---
elif st.session_state._pending_admin:
    name = st.session_state._pending_name
    st.info(
        f"{name}님은 관리자입니다. 비밀번호를 입력하거나 일반 회원으로 로그인하세요."
    )

    with st.form("admin_password_form"):
        password = st.text_input("비밀번호", type="password")
        col1, col2 = st.columns(2)
        with col1:
            admin_submit = st.form_submit_button("관리자 로그인")
        with col2:
            normal_submit = st.form_submit_button("일반 회원으로 로그인")

    if admin_submit:
        if password == st.secrets["admin"]["password"]:
            st.session_state.logged_in = True
            st.session_state.user_name = name
            st.session_state.is_admin = True
            st.session_state._pending_admin = False
            st.session_state._pending_name = None
            append_log("LOGIN", f"{name} 관리자 로그인")
            st.rerun()
        else:
            st.error("비밀번호가 올바르지 않습니다")

    if normal_submit:
        st.session_state.logged_in = True
        st.session_state.user_name = name
        st.session_state.is_admin = False
        st.session_state._pending_admin = False
        st.session_state._pending_name = None
        append_log("LOGIN", f"{name} 로그인")
        st.rerun()

# --- 로그인 폼 ---
else:
    with st.form("login_form"):
        name = st.text_input("이름")
        submitted = st.form_submit_button("로그인")

    if submitted:
        if not name.strip():
            st.warning("이름을 입력해주세요")
        elif not find_member(name.strip()):
            st.error("등록되지 않은 이름입니다. 관리자에게 등록을 요청하세요.")
        else:
            name = name.strip()
            admin_name = st.secrets["admin"]["name"]
            if name == admin_name:
                # 관리자 확인 단계로 전환
                st.session_state._pending_admin = True
                st.session_state._pending_name = name
                st.rerun()
            else:
                # 일반 회원 로그인
                st.session_state.logged_in = True
                st.session_state.user_name = name
                st.session_state.is_admin = False
                append_log("LOGIN", f"{name} 로그인")
                st.rerun()
