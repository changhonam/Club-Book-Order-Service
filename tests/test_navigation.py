"""네비게이션 페이지 목록 생성 로직 테스트"""

from unittest.mock import MagicMock, patch

import pytest


class TestBuildPageList:
    """build_page_list 테스트"""

    @pytest.fixture(autouse=True)
    def _mock_st_page(self):
        """st.Page를 mock하여 Streamlit 컨텍스트 없이 테스트"""

        def fake_page(path, *, title="", icon="", default=False):
            page = MagicMock()
            page.title = title
            page.icon = icon
            page.default = default
            page._path = path
            return page

        with patch("utils.navigation.st.Page", side_effect=fake_page) as mock:
            self.mock_page = mock
            yield

    def test_page_titles_logged_out(self):
        """비로그인 상태: 페이지 타이틀 순서 및 이름 확인"""
        from utils.navigation import build_page_list

        pages = build_page_list(logged_in=False, is_admin=False)
        titles = [p.title for p in pages]

        assert titles == ["홈", "로그인", "도서 구매 신청"]

    def test_page_titles_admin(self):
        """관리자 로그인: 페이지 타이틀 순서 및 이름 확인"""
        from utils.navigation import build_page_list

        pages = build_page_list(logged_in=True, is_admin=True)
        titles = [p.title for p in pages]

        assert titles == ["홈", "프로필", "도서 구매 신청", "Admin"]

    def test_home_is_default(self):
        """홈 페이지가 default=True로 설정됨"""
        from utils.navigation import build_page_list

        pages = build_page_list(logged_in=False, is_admin=False)

        home = pages[0]
        assert home.title == "홈"
        assert home.default is True

    def test_non_home_pages_not_default(self):
        """홈 외 페이지는 default=False"""
        from utils.navigation import build_page_list

        pages = build_page_list(logged_in=True, is_admin=True)

        for page in pages[1:]:
            assert page.default is False
