"""로그인 페이지 — 이름 + PIN 인증 + 관리자 비밀번호 인증."""

import streamlit as st

from utils.sheets import append_log, find_member, update_member_pin

# --- 이미 로그인 상태 ---
if st.session_state.logged_in:
    st.title("👤 프로필")
    role = "관리자" if st.session_state.is_admin else "회원"
    st.success(f"{st.session_state.user_name}님으로 로그인되어 있습니다 ({role})")

    st.divider()

    st.subheader("PIN 변경")
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
            if update_member_pin(st.session_state.user_name, new_pin):
                st.success("PIN이 변경되었습니다")
            else:
                st.error("PIN 변경에 실패했습니다")

# --- 관리자 비밀번호 입력 단계 ---
elif st.session_state._pending_admin:
    st.title("🔑 로그인")
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
            st.session_state.fee_paid = st.session_state._pending_fee_paid
            st.session_state._pending_admin = False
            st.session_state._pending_name = None
            st.session_state._pending_fee_paid = False
            append_log("LOGIN", f"{name} 관리자 로그인")
            st.rerun()
        else:
            st.error("비밀번호가 올바르지 않습니다")

    if normal_submit:
        st.session_state.logged_in = True
        st.session_state.user_name = name
        st.session_state.is_admin = False
        st.session_state.fee_paid = st.session_state._pending_fee_paid
        st.session_state._pending_admin = False
        st.session_state._pending_name = None
        st.session_state._pending_fee_paid = False
        append_log("LOGIN", f"{name} 로그인")
        st.rerun()

# --- 로그인 폼 ---
else:
    st.title("🔑 로그인")
    with st.form("login_form"):
        name = st.text_input("이름")
        pin = st.text_input("PIN (4자리)", type="password", max_chars=4)
        submitted = st.form_submit_button("로그인")

    if submitted:
        if not name.strip():
            st.warning("이름을 입력해주세요")
        else:
            member = find_member(name.strip())
            if member is None:
                st.error("등록되지 않은 이름입니다. 관리자에게 등록을 요청하세요.")
            elif pin != member.pin:
                st.error("PIN이 올바르지 않습니다")
            else:
                name = name.strip()
                admin_name = st.secrets["admin"]["name"]
                if name == admin_name:
                    # 관리자 확인 단계로 전환
                    st.session_state._pending_admin = True
                    st.session_state._pending_name = name
                    st.session_state._pending_fee_paid = member.fee_paid
                    st.rerun()
                else:
                    # 일반 회원 로그인
                    st.session_state.logged_in = True
                    st.session_state.user_name = name
                    st.session_state.is_admin = False
                    st.session_state.fee_paid = member.fee_paid
                    append_log("LOGIN", f"{name} 로그인")
                    st.rerun()
