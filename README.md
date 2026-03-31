# 독서동호회 도서 구매 신청 서비스

독서동호회 회원들이 Yes24 도서 링크로 구매 신청하고, 동호회 지원금 기반 본인 부담금을 자동 정산받으며, 관리자가 일괄 구매를 진행할 수 있는 사내 웹 서비스입니다.

## 주요 기능

- **도서 신청**: Yes24 URL 입력만으로 도서 정보 자동 조회 및 신청
- **자동 정산**: 동호회 지원금(최대 30,000원) 자동 계산, 본인 부담금 확인
- **관리자 기능**: 회원 관리, 회비 관리, 신청 현황 조회, 대리 신청, Excel 내보내기
- **자동 마감**: 지정 일시에 자동으로 신청 마감

## 기술 스택

| 구분 | 기술 |
|------|------|
| Framework | Python + Streamlit |
| Database | Google Sheets (gspread) |
| Hosting | Streamlit Community Cloud |
| Scraping | requests + BeautifulSoup4 |
| Export | openpyxl (Excel) |
| Test | pytest |
| Formatting | ruff |

## 시작하기

### 1. 사전 준비

#### Google Cloud 설정

1. [Google Cloud Console](https://console.cloud.google.com/)에서 프로젝트 생성
2. 아래 두 API를 활성화:
   - **Google Sheets API**
   - **Google Drive API**
3. **서비스 계정** 생성 후 JSON 키 다운로드:
   - API 및 서비스 > 사용자 인증 정보 > 서비스 계정 생성
   - 키 탭 > 키 추가 > JSON

#### Google Sheets 준비

1. Google Sheets에서 스프레드시트 1개 생성
2. 서비스 계정 이메일(`client_email`)을 **편집자** 권한으로 공유

### 2. 의존성 설치

```bash
pip install -r requirements.txt
```

### 3. secrets.toml 설정

`.streamlit/secrets.toml` 파일을 생성하고 아래 내용을 채웁니다. (이 파일은 `.gitignore`에 포함되어 있어 커밋되지 않습니다.)

```toml
[gcp_service_account]
type = "service_account"
project_id = ""
private_key_id = ""
private_key = ""
client_email = ""
client_id = ""
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = ""

[spreadsheet]
name = "스프레드시트 이름"

[admin]
name = "관리자 이름"
password = "관리자 비밀번호"
```

- `[gcp_service_account]`: 다운로드한 JSON 키의 각 필드를 그대로 복사
- `[spreadsheet].name`: 생성한 Google Sheets 스프레드시트 이름과 동일하게 입력
- `[admin].name`: Members 시트에 등록된 관리자 이름과 동일하게 입력
- `[admin].password`: 관리자 로그인 시 사용할 비밀번호

### 4. Google Sheets 초기 설정

스프레드시트 내 워크시트(탭)와 헤더를 자동으로 생성하는 스크립트를 실행합니다.

```bash
python scripts/setup_sheets.py
```

이 스크립트는 다음 4개 워크시트를 생성합니다:

| 워크시트 | 헤더 | 설명 |
|----------|------|------|
| Members | `Name`, `PIN`, `Fee_Paid` | 회원 명부 (PIN: 4자리, Fee_Paid: 회비 납부 여부) |
| Orders | `Order_ID`, `Order_Month`, `Name`, `Book_URL`, `Title`, `Author`, `Price`, `Created_At` | 주문 내역 |
| Config | `Key`, `Value` | 서비스 설정 (접수월, 마감 여부, 자동마감 일시) |
| Logs | `Timestamp`, `Event_Type`, `Message` | 이벤트 로그 |

### 5. 앱 실행

```bash
streamlit run app.py
```

브라우저에서 `http://localhost:8501`로 접속합니다.

## 프로젝트 구조

```
├── app.py                      # Streamlit 메인 앱 (자동마감 체크, 사이드바)
├── pages/
│   ├── 1_login.py              # 로그인 (이름 + PIN 인증, 관리자 비밀번호)
│   ├── 2_dashboard.py          # 대시보드 (도서 신청, 정산 조회)
│   └── 3_admin.py              # 관리자 (회원/주문/회비 관리, 대리 신청, Excel 내보내기)
├── utils/
│   ├── __init__.py             # 데이터 모델 (BookInfo, Settlement, OrderRecord, MemberRecord, ConfigRecord)
│   ├── sheets.py               # Google Sheets CRUD (캐싱, 재시도 포함)
│   ├── scraper.py              # Yes24 도서 정보 스크래핑
│   └── settlement.py           # 정산 로직 (지원금 계산, 주문별 배분)
├── scripts/
│   └── setup_sheets.py         # Google Sheets 초기 설정 스크립트
├── tests/
│   ├── conftest.py             # 테스트 공통 픽스처
│   ├── test_scraper.py         # 스크래퍼 테스트
│   ├── test_settlement.py      # 정산 로직 테스트
│   ├── test_sheets.py          # Sheets CRUD 테스트
│   ├── test_members.py         # 회원 관리(PIN, 회비) 테스트
│   └── test_integration.py     # 통합 테스트
├── docs/
│   ├── PRD.md                  # 제품 요구사항 정의서
│   └── TRD.md                  # 기술 요구사항 정의서
├── .streamlit/
│   ├── config.toml             # Streamlit 테마/서버 설정
│   └── secrets.toml            # 인증 정보 (gitignore 대상)
└── requirements.txt
```

## 정산 로직

```
동호회 지원금 = floor(min(월 총액 / 2, 30000))
본인 부담금 = 월 총액 - 지원금
```

- 동호회가 총액의 50%를 지원하되, 월 최대 30,000원까지 지원
- 여러 건 신청 시 지원금은 각 주문의 가격 비율에 따라 배분

## 배포 (Streamlit Community Cloud)

1. GitHub에 코드 푸시 (secrets.toml 제외)
2. [Streamlit Community Cloud](https://share.streamlit.io/)에서 앱 생성
3. GitHub 저장소 연결 후 `app.py`를 메인 파일로 지정
4. **Advanced settings > Secrets**에 `secrets.toml` 내용을 붙여넣기

## 테스트

```bash
pytest
```
