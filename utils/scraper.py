"""Yes24 도서 정보 스크래핑 모듈"""

import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from utils import BookInfo

# ---------------------------------------------------------------------------
# CSS 셀렉터 상수 (Yes24 PC 페이지 기준)
# ---------------------------------------------------------------------------
SEL_TITLE = "h2.gd_name"
SEL_AUTHOR = "span.gd_pubArea a"  # 저자 링크
SEL_PUBLISHER = "span.gd_pub a"  # 출판사 링크
SEL_SALE_PRICE = ".nor_price"  # 판매가 금액 (가격 영역 내)
SEL_ORIGINAL_PRICE = "em.yes_b"  # 정가 금액 (fallback)
SEL_SOLDOUT = "div.btn_B_wrap, div.gd_sellout"  # 품절/절판 영역
SEL_EBOOK_CATEGORY = "div.gd_infoTop span"  # 카테고리 정보

# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 30

# Yes24 URL 패턴
_RE_GOODS_ID = re.compile(r"/(?:Product/)?Goods/(?:Detail/)?(\d+)", re.IGNORECASE)
_VALID_HOSTS = {"www.yes24.com", "m.yes24.com", "yes24.com"}


class ScrapingError(Exception):
    """스크래핑 실패 시 발생하는 예외"""


# ---------------------------------------------------------------------------
# URL 정규화
# ---------------------------------------------------------------------------
def normalize_yes24_url(url: str) -> str:
    """m.yes24.com URL을 www.yes24.com으로 변환. 이미 www면 그대로 반환.

    Raises:
        ValueError: 유효하지 않은 Yes24 URL
    """
    url = url.strip()

    # scheme이 없으면 https 추가
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    parsed = urlparse(url)
    host = parsed.hostname or ""

    if host not in _VALID_HOSTS:
        raise ValueError(f"유효하지 않은 Yes24 URL입니다: {url}")

    match = _RE_GOODS_ID.search(parsed.path)
    if not match:
        raise ValueError(f"상품번호를 찾을 수 없습니다: {url}")

    goods_id = match.group(1)
    return f"https://www.yes24.com/Product/Goods/{goods_id}"


def extract_goods_id(url: str) -> str | None:
    """Yes24 URL에서 상품번호만 추출. 실패 시 None."""
    try:
        normalized = normalize_yes24_url(url)
    except ValueError:
        return None
    match = _RE_GOODS_ID.search(normalized)
    return match.group(1) if match else None


# ---------------------------------------------------------------------------
# 가격 파싱 헬퍼
# ---------------------------------------------------------------------------
def _parse_price(text: str) -> int:
    """'18,000원' 같은 문자열에서 정수 가격을 추출한다."""
    cleaned = re.sub(r"[^\d]", "", text)
    if not cleaned:
        raise ScrapingError(f"가격을 파싱할 수 없습니다: {text!r}")
    return int(cleaned)


def _extract_sale_price(soup: BeautifulSoup) -> int:
    """판매가를 추출한다. 판매가가 없으면 정가를 사용한다."""
    # 가격 테이블에서 '판매가' 행 찾기 (.nor_price 우선)
    price_rows = soup.select("tr")
    for row in price_rows:
        row_text = row.get_text()

        # 크레마머니 최대혜택가 제외
        if "크레마" in row_text:
            continue

        if "판매가" in row_text:
            # .nor_price 우선 시도 (Yes24 실제 구조)
            nor_price = row.select_one(SEL_SALE_PRICE)
            if nor_price:
                return _parse_price(nor_price.get_text(strip=True))
            # fallback: em.yes_b
            price_em = row.select_one(SEL_ORIGINAL_PRICE)
            if price_em:
                return _parse_price(price_em.get_text(strip=True))

    # 판매가가 없으면 정가 찾기
    for row in price_rows:
        row_text = row.get_text()
        if "정가" in row_text and "크레마" not in row_text:
            nor_price = row.select_one(SEL_SALE_PRICE)
            if nor_price:
                return _parse_price(nor_price.get_text(strip=True))
            price_em = row.select_one(SEL_ORIGINAL_PRICE)
            if price_em:
                return _parse_price(price_em.get_text(strip=True))

    # 테이블 외부에서 가격 찾기
    price_el = soup.select_one(SEL_SALE_PRICE)
    if price_el:
        return _parse_price(price_el.get_text(strip=True))

    raise ScrapingError("가격 정보를 찾을 수 없습니다")


# ---------------------------------------------------------------------------
# ISBN 추출
# ---------------------------------------------------------------------------
_RE_ISBN13 = re.compile(r"97[89]\d{10}")


def _extract_isbn(soup: BeautifulSoup) -> str:
    """ISBN-13을 추출한다. 찾지 못하면 빈 문자열 반환."""
    import json

    # 1순위: JSON-LD 구조화 데이터
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or "")
            # 단일 객체 또는 리스트
            items = data if isinstance(data, list) else [data]
            for item in items:
                isbn = item.get("isbn", "")
                if isbn and _RE_ISBN13.match(isbn):
                    return isbn
        except (json.JSONDecodeError, AttributeError):
            continue

    # 2순위: #infoset_specific 테이블에서 ISBN13 행
    info_section = soup.select_one("#infoset_specific")
    if info_section:
        for row in info_section.select("tr"):
            cells = row.select("td, th")
            if len(cells) >= 2 and "ISBN13" in cells[0].get_text():
                isbn_text = cells[1].get_text(strip=True)
                match = _RE_ISBN13.search(isbn_text)
                if match:
                    return match.group()

    return ""


# ---------------------------------------------------------------------------
# 구매 가능 여부 판별
# ---------------------------------------------------------------------------
def _check_availability(soup: BeautifulSoup, url: str) -> tuple[bool, str | None]:
    """구매 가능 여부를 판별하고 (is_available, reason)을 반환한다."""

    # eBook 판별: URL 경로에 /eBook/이 포함된 경우
    if "/eBook/" in url or "/ebook/" in url:
        return False, "eBook"

    # eBook 판별: 상품 제목 영역(gd_titArea)에 "eBook" 텍스트가 있는 경우
    tit_area = soup.select_one("div.gd_titArea")
    if tit_area:
        tit_text = tit_area.get_text(strip=True)
        if "eBook" in tit_text:
            return False, "eBook"

    # eBook 판별: gd_ebook 클래스
    if soup.select("em.gd_ebook, span.gd_ebook"):
        return False, "eBook"

    # 품절/절판 판별: 구매 버튼 영역에서 확인
    buy_area = soup.select_one("div.gd_buy, div.btn_B_wrap")
    if buy_area:
        buy_text = buy_area.get_text()
        if "품절" in buy_text:
            return False, "품절"
        if "절판" in buy_text:
            return False, "절판"

    # 품절/절판 판별: 판매 상태 영역 (gd_saleState, gd_action 등)
    sale_state_el = soup.select_one("p.gd_saleState, div.gd_actionCont")
    if sale_state_el:
        state_text = sale_state_el.get_text(strip=True)
        if "품절" in state_text:
            return False, "품절"
        if "절판" in state_text:
            return False, "절판"

    # 버튼 영역이 없거나 별도 품절 표시가 있는 경우
    soldout_el = soup.select_one("div.gd_sellout, em.gd_state")
    if soldout_el:
        soldout_text = soldout_el.get_text(strip=True)
        if "품절" in soldout_text:
            return False, "품절"
        if "절판" in soldout_text:
            return False, "절판"

    return True, None


# ---------------------------------------------------------------------------
# 메인 스크래핑 함수
# ---------------------------------------------------------------------------
def scrape_book_info(url: str) -> BookInfo:
    """Yes24 URL에서 도서 정보를 스크래핑.

    - User-Agent 헤더 설정
    - 타임아웃 10초
    - '판매가' 기준 가격 파싱 (크레마머니 제외)
    - 품절/절판/eBook 판별

    Raises:
        ScrapingError: 스크래핑 실패 시
    """
    try:
        normalized_url = normalize_yes24_url(url)
    except ValueError as e:
        raise ScrapingError(str(e)) from e

    headers = {"User-Agent": USER_AGENT}

    try:
        response = requests.get(
            normalized_url, headers=headers, timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
    except requests.exceptions.Timeout as e:
        raise ScrapingError(f"요청 시간 초과: {normalized_url}") from e
    except requests.exceptions.RequestException as e:
        raise ScrapingError(f"HTTP 요청 실패: {e}") from e

    response.encoding = "utf-8"
    soup = BeautifulSoup(response.text, "html.parser")

    # 제목 추출
    title_el = soup.select_one(SEL_TITLE)
    if not title_el:
        raise ScrapingError("도서 제목을 찾을 수 없습니다")
    title = title_el.get_text(strip=True)

    # 저자 추출
    author_el = soup.select_one(SEL_AUTHOR)
    if not author_el:
        raise ScrapingError("저자 정보를 찾을 수 없습니다")
    author = author_el.get_text(strip=True)

    # 출판사 추출
    publisher_el = soup.select_one(SEL_PUBLISHER)
    if not publisher_el:
        raise ScrapingError("출판사 정보를 찾을 수 없습니다")
    publisher = publisher_el.get_text(strip=True)

    # 가격 추출
    price = _extract_sale_price(soup)

    # ISBN 추출 (실패해도 에러 발생하지 않음)
    isbn = _extract_isbn(soup)

    # 구매 가능 여부 판별
    is_available, unavailable_reason = _check_availability(soup, normalized_url)

    return BookInfo(
        title=title,
        author=author,
        publisher=publisher,
        price=price,
        url=normalized_url,
        is_available=is_available,
        unavailable_reason=unavailable_reason,
        isbn=isbn,
    )
