# TRD (기술 요구사항 정의서)

## 2.1. 시스템 아키텍처 및 기술 스택
- **Framework**: Python + Streamlit
- **Hosting**: Streamlit Community Cloud
- **Database**: Google Sheets API (gspread, pandas 라이브러리 사용)

## 2.2. 데이터베이스 스키마 (Google Sheets 구조)

스프레드시트 파일 내에 4개의 시트(Sheet)를 운영한다.

### [Sheet 1: Members]
| 컬럼 | 타입 | 설명 |
|------|------|------|
| Name | String | 회원 이름 (PK 역할, 고유하게 등록됨) |
| PIN | String | 4자리 숫자 PIN (기본값: "0000") |
| Fee_Paid | String | 회비 납부 여부 ("true"/"false", 기본값: "false") |

### [Sheet 2: Orders]
| 컬럼 | 타입 | 설명 |
|------|------|------|
| Order_ID | String (UUID4) | 고유 신청 번호 |
| Order_Month | String | 신청 월 (YYYY-MM, 관리자가 설정한 현재 접수 월 값) |
| Name | String | 신청자 이름 |
| Book_URL | String | Yes24 도서 URL |
| Title | String | 책 제목 |
| Author | String | 저자 |
| Price | Integer | 판매가 |
| Created_At | Timestamp | 신청 일시 (YYYY-MM-DD HH:MM:SS) |
| Publisher | String | 출판사 (빈 문자열 허용) |
| ISBN | String | ISBN-13 (빈 문자열 허용, 스크래핑 실패 시 빈 값) |

### [Sheet 3: Config]
| Key | Value | 설명 |
|-----|-------|------|
| current_order_month | "2026-03" | 현재 신청 접수 중인 월 |
| is_closed | "false" | 신청 마감 여부 ("true"/"false") |
| auto_close_datetime | "" | 자동 마감 예약 일시 (YYYY-MM-DD HH:MM 또는 빈 값) |

### [Sheet 4: Logs]
| 컬럼 | 타입 | 설명 |
|------|------|------|
| Timestamp | String | YYYY-MM-DD HH:MM:SS |
| Event_Type | String | 이벤트 유형 |
| Message | String | 상세 메시지 |

**Event_Type**: ORDER_CREATE, ORDER_DELETE, ADMIN_BULK_DELETE, ADMIN_CLOSE_MONTH, ADMIN_SET_MONTH, MEMBER_ADD, MEMBER_DELETE, PIN_RESET, FEE_PAID, FEE_PAID_BATCH, FEE_RESET_ALL

**보존 기간**: 무기한. 관리자 페이지에서 최근 50건 조회.

## 2.3. Google Sheets API 연동 및 성능 최적화

**인증**: `st.secrets["gcp_service_account"]`

**캐싱 전략 (함수별 개별 캐싱)**:
- Spreadsheet 객체: `@st.cache_resource` (반복 `client.open()` 호출 방지)
- Members: `@st.cache_data(ttl=600)`
- Orders: `@st.cache_data(ttl=300)`
- Config: `@st.cache_data(ttl=60)`
- 변경 시 해당 함수 캐시만 선택적 초기화 (`get_orders_by_month.clear()` 등)
- Orders 원본 조회(`_get_all_orders_raw`)를 별도 캐싱하여 월별/월 목록 조회 시 API 호출 공유

**동시성 처리**:
- 추가: `append_row()` 그대로 사용
- 삭제: Order_ID로 존재 확인 후 삭제
- 일괄 변경: `worksheet.batch_update()`로 다건 셀 업데이트를 1회 API 호출로 처리
- API 에러 시 최대 3회 재시도 (지수 백오프 + jitter), 400/403 에러는 즉시 실패

## 2.4. Streamlit 상태 관리
- `st.session_state.logged_in`, `st.session_state.user_name`
- `st.session_state.is_admin`
- `st.session_state.fee_paid` (회비 납부 여부)
- `st.session_state.scraped_data` (스크래핑 결과 보존)

## 2.5. 핵심 기술 구현

### 2.5.1. Yes24 웹 스크래핑
- **라이브러리**: requests, BeautifulSoup4, User-Agent 헤더 필수
- **URL 전처리**: m.yes24.com → www.yes24.com 자동 변환
- **가격 파싱**: '판매가' 표기 가격 추출, '크레마머니 최대혜택가' 제외
- **eBook 필터링**: 'eBook', '크레마' 포함 시 차단
- **오류 Fallback**: try-except, st.error() 안내, 일반 회원 수동 입력 불허

### 2.5.2. 자동 마감 예약
- Streamlit Cloud는 cron 미지원 → **접속 시 체크 방식**
- 페이지 로드마다 auto_close_datetime 경과 여부 확인, 경과 시 is_closed="true" 전환

### 2.5.3. 비용 정산 알고리즘
```python
import math
def calculate_monthly_payment(monthly_total_price):
    max_support = 30000
    club_support = math.floor(min(monthly_total_price / 2, max_support))
    user_payment = monthly_total_price - club_support
    return club_support, user_payment
```

## 2.6. UI/UX 가이드라인
- Streamlit 기본 반응형 레이아웃 활용
- `st.dataframe()` (가로 스크롤), `width="stretch"`
- 별도 모바일 전용 레이아웃 불필요
