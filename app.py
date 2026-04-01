"""독서동호회 도서 구매 신청 서비스 - 메인 앱"""

from datetime import datetime
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")

import streamlit as st

from utils.navigation import build_page_list
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
        auto_close_dt = datetime.strptime(config.auto_close_datetime, "%Y-%m-%d %H:%M").replace(tzinfo=KST)
        if datetime.now(KST) >= auto_close_dt:
            update_config(is_closed=True)
            append_log(
                "ADMIN_CLOSE_MONTH",
                f"{config.current_order_month} 자동마감 실행",
            )
    except ValueError:
        pass

# --- 사이드바 ---
render_sidebar()

# --- 네비게이션 ---
pages = build_page_list(
    logged_in=st.session_state.logged_in,
    is_admin=st.session_state.is_admin,
)
pg = st.navigation(pages)
pg.run()
