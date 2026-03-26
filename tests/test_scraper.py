"""Yes24 스크래핑 모듈 테스트

모든 테스트는 fixture HTML 파일 기반으로 동작하며 실제 네트워크 호출을 하지 않는다.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from utils.scraper import ScrapingError, normalize_yes24_url, scrape_book_info

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
            f"{status_code} Error"
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
        """timeout=10을 설정한다"""
        html = _load_fixture("yes24_normal.html")
        mock_get.return_value = _mock_response(html)

        scrape_book_info("https://www.yes24.com/Product/Goods/91288143")

        call_kwargs = mock_get.call_args
        timeout = call_kwargs.kwargs.get("timeout", call_kwargs[1].get("timeout"))
        assert timeout == 10


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


class TestScrapeBookInfoErrors:
    """오류 처리 테스트"""

    @patch("utils.scraper.requests.get")
    def test_http_error(self, mock_get):
        """HTTP 오류 시 ScrapingError 발생"""
        mock_get.return_value = _mock_response("", status_code=404)

        with pytest.raises(ScrapingError, match="HTTP 요청 실패"):
            scrape_book_info("https://www.yes24.com/Product/Goods/99999999")

    @patch("utils.scraper.requests.get")
    def test_timeout_error(self, mock_get):
        """타임아웃 시 ScrapingError 발생"""
        mock_get.side_effect = requests.exceptions.Timeout("timeout")

        with pytest.raises(ScrapingError, match="시간 초과"):
            scrape_book_info("https://www.yes24.com/Product/Goods/99999999")

    @patch("utils.scraper.requests.get")
    def test_connection_error(self, mock_get):
        """연결 실패 시 ScrapingError 발생"""
        mock_get.side_effect = requests.exceptions.ConnectionError("fail")

        with pytest.raises(ScrapingError, match="HTTP 요청 실패"):
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
