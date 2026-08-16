"""Yes24 스크래핑 모듈 테스트

모든 테스트는 fixture HTML 파일 기반으로 동작하며 실제 네트워크 호출을 하지 않는다.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests


import utils.scraper as _scraper_mod
from utils.scraper import ScrapingError, normalize_yes24_url, scrape_book_info

_extract_isbn = _scraper_mod._extract_isbn
_extract_author = _scraper_mod._extract_author

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _load_fixture(filename: str) -> str:
    return (FIXTURES_DIR / filename).read_text(encoding="utf-8")


def _mock_response(html: str, status_code: int = 200) -> MagicMock:
    """requests.get 반환값을 흉내 내는 Mock 객체를 만든다."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = html
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.exceptions.HTTPError(
            f"{status_code} Error", response=resp
        )
    return resp


# ===========================================================================
# normalize_yes24_url 테스트
# ===========================================================================
class TestNormalizeYes24Url:
    """URL 정규화 함수 테스트"""

    def test_mobile_url_to_www(self):
        """m.yes24.com → www.yes24.com 변환"""
        result = normalize_yes24_url("https://m.yes24.com/Goods/Detail/12345")
        assert result == "https://www.yes24.com/Product/Goods/12345"

    def test_www_url_unchanged(self):
        """이미 www.yes24.com이면 그대로 유지"""
        result = normalize_yes24_url("https://www.yes24.com/Product/Goods/12345678")
        assert result == "https://www.yes24.com/Product/Goods/12345678"

    def test_http_to_https(self):
        """http → https 통일"""
        result = normalize_yes24_url("http://www.yes24.com/Product/Goods/99999")
        assert result == "https://www.yes24.com/Product/Goods/99999"

    def test_strip_query_params(self):
        """쿼리 파라미터 제거"""
        result = normalize_yes24_url(
            "https://www.yes24.com/Product/Goods/12345?OzSrank=1&foo=bar"
        )
        assert result == "https://www.yes24.com/Product/Goods/12345"

    def test_bare_domain(self):
        """yes24.com (서브도메인 없음)"""
        result = normalize_yes24_url("https://yes24.com/Product/Goods/55555")
        assert result == "https://www.yes24.com/Product/Goods/55555"

    def test_no_scheme(self):
        """scheme 없는 URL"""
        result = normalize_yes24_url("m.yes24.com/Goods/Detail/77777")
        assert result == "https://www.yes24.com/Product/Goods/77777"

    def test_invalid_domain_raises(self):
        """yes24.com이 아닌 도메인 → ValueError"""
        with pytest.raises(ValueError, match="유효하지 않은"):
            normalize_yes24_url("https://www.kyobobooks.co.kr/product/1234")

    def test_no_goods_id_raises(self):
        """상품번호가 없는 URL → ValueError"""
        with pytest.raises(ValueError, match="상품번호"):
            normalize_yes24_url("https://www.yes24.com/Main/default.aspx")


# ===========================================================================
# scrape_book_info 테스트
# ===========================================================================
class TestScrapeBookInfoNormal:
    """정상 도서 파싱 테스트"""

    @patch("utils.scraper.requests.get")
    def test_parse_normal_book(self, mock_get):
        """정상 구매 가능 도서를 올바르게 파싱한다"""
        html = _load_fixture("yes24_normal.html")
        mock_get.return_value = _mock_response(html)

        book = scrape_book_info("https://www.yes24.com/Product/Goods/91288143")

        assert book.title == "클린 코드 Clean Code"
        assert book.author == "로버트 C. 마틴"
        assert book.publisher == "인사이트"
        assert book.price == 29700  # 판매가
        assert book.url == "https://www.yes24.com/Product/Goods/91288143"
        assert book.is_available is True
        assert book.unavailable_reason is None
        assert book.isbn == "9788966260959"

    @patch("utils.scraper.requests.get")
    def test_uses_user_agent(self, mock_get):
        """User-Agent 헤더를 설정한다"""
        html = _load_fixture("yes24_normal.html")
        mock_get.return_value = _mock_response(html)

        scrape_book_info("https://www.yes24.com/Product/Goods/91288143")

        call_kwargs = mock_get.call_args
        assert "User-Agent" in call_kwargs.kwargs.get(
            "headers", call_kwargs[1].get("headers", {})
        )

    @patch("utils.scraper.requests.get")
    def test_uses_timeout(self, mock_get):
        """timeout=30을 설정한다"""
        html = _load_fixture("yes24_normal.html")
        mock_get.return_value = _mock_response(html)

        scrape_book_info("https://www.yes24.com/Product/Goods/91288143")

        call_kwargs = mock_get.call_args
        timeout = call_kwargs.kwargs.get("timeout", call_kwargs[1].get("timeout"))
        assert timeout == 30


class TestScrapeBookInfoUsed:
    """중고도서 파싱 테스트 (저자가 링크가 아닌 일반 텍스트)"""

    @patch("utils.scraper.requests.get")
    def test_parse_used_book(self, mock_get):
        """중고도서에서 출판사를 저자로 잘못 읽지 않는다"""
        html = _load_fixture("yes24_used.html")
        mock_get.return_value = _mock_response(html)

        book = scrape_book_info("https://www.yes24.com/Product/Goods/123456789")

        assert book.title == "하룻밤에 읽는 성서이야기"
        assert book.author == "이쿠타 사토시"
        assert book.publisher == "랜덤하우스코리아"
        assert book.price == 4500  # 중고판매가
        assert book.is_available is True
        assert book.unavailable_reason is None
        assert book.isbn == "9788959131365"


class TestExtractAuthor:
    """저자 추출 헬퍼 함수 테스트"""

    @staticmethod
    def _soup(pub_area_html: str):
        from bs4 import BeautifulSoup

        return BeautifulSoup(
            f"<html><body>{pub_area_html}</body></html>", "html.parser"
        )

    def test_plain_text_author(self):
        """중고도서: gd_auth가 텍스트, gd_pub만 링크"""
        soup = self._soup(
            """
            <span class="gd_pubArea">
                <span class="gd_auth">이쿠타 사토시</span>
                <em class="divi">|</em>
                <span class="gd_pub"><a href="#">랜덤하우스코리아</a></span>
                <em class="divi">|</em>
                <span class="gd_date">2003년 11월 06일</span>
            </span>
            """
        )
        assert _extract_author(soup, "랜덤하우스코리아") == "이쿠타 사토시"

    def test_linked_author_in_gd_auth(self):
        """일반 도서: gd_auth 안의 저자 링크를 사용한다"""
        soup = self._soup(
            """
            <span class="gd_pubArea">
                <span class="gd_auth"><a href="#">한강</a> 저</span>
                <em class="divi">|</em>
                <span class="gd_pub"><a href="#">창비</a></span>
                <em class="divi">|</em>
                <span class="gd_date">2014년 05월 19일</span>
                <span class="gd_orgin">번역서 : <a href="#">Human Acts</a></span>
            </span>
            """
        )
        assert _extract_author(soup, "창비") == "한강"

    def test_role_suffix_stripped_from_plain_text(self):
        """텍스트 저자의 역할 표기('저 / 역')를 제거한다"""
        soup = self._soup(
            """
            <span class="gd_pubArea">
                <span class="gd_auth">마르쿠스 핫슈타인 저 / 김지원 역</span>
                <em class="divi">|</em>
                <span class="gd_pub"><a href="#">수막새</a></span>
            </span>
            """
        )
        assert _extract_author(soup, "수막새") == "마르쿠스 핫슈타인"

    def test_gd_auth_absent_uses_non_publisher_link(self):
        """gd_auth가 없는 마크업이면 출판사 링크를 제외한 첫 링크를 쓴다"""
        soup = self._soup(
            """
            <span class="gd_pubArea">
                <a href="#">로버트 C. 마틴</a> 저
                <span class="gd_pub"><a href="#">인사이트</a></span>
            </span>
            """
        )
        assert _extract_author(soup, "인사이트") == "로버트 C. 마틴"

    def test_no_author_raises(self):
        """저자가 없는 상품(예: 음반)은 출판사를 저자로 쓰지 않고 실패한다"""
        soup = self._soup(
            """
            <span class="gd_pubArea">
                <span class="gd_pub"><a href="#">뮤직리서치</a></span>
                <em class="divi">|</em>
                <span class="gd_date">2008년 09월 04일</span>
            </span>
            """
        )
        with pytest.raises(ScrapingError, match="저자"):
            _extract_author(soup, "뮤직리서치")


class TestScrapeBookInfoSoldout:
    """품절 도서 판별 테스트"""

    @patch("utils.scraper.requests.get")
    def test_soldout_book(self, mock_get):
        """품절 도서를 올바르게 판별한다"""
        html = _load_fixture("yes24_soldout.html")
        mock_get.return_value = _mock_response(html)

        book = scrape_book_info("https://www.yes24.com/Product/Goods/55555555")

        assert book.title == "오래된 소설책"
        assert book.author == "김작가"
        assert book.publisher == "문학동네"
        assert book.price == 13500
        assert book.is_available is False
        assert book.unavailable_reason == "품절"
        assert book.isbn == "9788954699952"


class TestScrapeBookInfoEbook:
    """eBook 필터 테스트"""

    @patch("utils.scraper.requests.get")
    def test_ebook_detected(self, mock_get):
        """eBook을 올바르게 판별한다"""
        html = _load_fixture("yes24_ebook.html")
        mock_get.return_value = _mock_response(html)

        book = scrape_book_info("https://www.yes24.com/Product/Goods/77777777")

        assert book.title == "파이썬 완벽 가이드"
        assert book.author == "이파이썬"
        assert book.publisher == "한빛미디어"
        assert book.price == 20000  # 판매가 (크레마머니 최대혜택가 17,000이 아님)
        assert book.is_available is False
        assert book.unavailable_reason == "eBook"
        assert book.isbn == ""  # eBook fixture에는 ISBN 없음


class TestScrapeBookInfoErrors:
    """오류 처리 테스트"""

    @patch("utils.scraper.requests.get")
    def test_http_error(self, mock_get):
        """HTTP 오류 시 ScrapingError 발생"""
        mock_get.return_value = _mock_response("", status_code=404)

        with pytest.raises(ScrapingError, match="HTTP 404 오류"):
            scrape_book_info("https://www.yes24.com/Product/Goods/99999999")

    @patch("utils.scraper.requests.get")
    def test_timeout_error(self, mock_get):
        """읽기 타임아웃 시 ScrapingError 발생"""
        mock_get.side_effect = requests.exceptions.ReadTimeout("timeout")

        with pytest.raises(ScrapingError, match="읽기 타임아웃"):
            scrape_book_info("https://www.yes24.com/Product/Goods/99999999")

    @patch("utils.scraper.requests.get")
    def test_connection_error(self, mock_get):
        """연결 실패 시 ScrapingError 발생"""
        mock_get.side_effect = requests.exceptions.ConnectionError("fail")

        with pytest.raises(ScrapingError, match="연결 오류"):
            scrape_book_info("https://www.yes24.com/Product/Goods/99999999")

    def test_invalid_url(self):
        """잘못된 URL → ScrapingError"""
        with pytest.raises(ScrapingError):
            scrape_book_info("https://www.kyobobooks.co.kr/product/1234")

    @patch("utils.scraper.requests.get")
    def test_missing_title_raises(self, mock_get):
        """제목 요소가 없으면 ScrapingError"""
        html = "<html><body><p>빈 페이지</p></body></html>"
        mock_get.return_value = _mock_response(html)

        with pytest.raises(ScrapingError, match="제목"):
            scrape_book_info("https://www.yes24.com/Product/Goods/11111111")


# ===========================================================================
# _extract_isbn 단위 테스트
# ===========================================================================
class TestExtractIsbn:
    """ISBN 추출 헬퍼 함수 테스트"""

    def test_extract_from_json_ld(self):
        """JSON-LD 구조화 데이터에서 ISBN 추출"""
        from bs4 import BeautifulSoup

        html = """
        <html><head>
        <script type="application/ld+json">
        {"@type": "Book", "isbn": "9788966260959"}
        </script>
        </head><body></body></html>
        """
        soup = BeautifulSoup(html, "html.parser")
        assert _extract_isbn(soup) == "9788966260959"

    def test_extract_from_infoset_table(self):
        """#infoset_specific 테이블에서 ISBN13 추출"""
        from bs4 import BeautifulSoup

        html = """
        <html><body>
        <div id="infoset_specific">
            <table><tbody>
                <tr><td>ISBN13</td><td>9788954699952</td></tr>
            </tbody></table>
        </div>
        </body></html>
        """
        soup = BeautifulSoup(html, "html.parser")
        assert _extract_isbn(soup) == "9788954699952"

    def test_json_ld_takes_priority(self):
        """JSON-LD와 테이블 모두 있으면 JSON-LD 우선"""
        from bs4 import BeautifulSoup

        html = """
        <html><head>
        <script type="application/ld+json">
        {"@type": "Book", "isbn": "9781111111111"}
        </script>
        </head><body>
        <div id="infoset_specific">
            <table><tbody>
                <tr><td>ISBN13</td><td>9782222222222</td></tr>
            </tbody></table>
        </div>
        </body></html>
        """
        soup = BeautifulSoup(html, "html.parser")
        assert _extract_isbn(soup) == "9781111111111"

    def test_no_isbn_returns_empty(self):
        """ISBN 정보 없으면 빈 문자열"""
        from bs4 import BeautifulSoup

        html = "<html><body><p>ISBN 없는 페이지</p></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        assert _extract_isbn(soup) == ""
