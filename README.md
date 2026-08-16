# 독서동호회 도서 구매 신청 서비스

독서동호회 회원들이 Yes24 도서 링크로 구매 신청하고, 동호회 지원금 기반 본인 부담금을 자동 정산받으며, 관리자가 일괄 구매를 진행할 수 있는 사내 웹 서비스입니다.

## 주요 기능

- **도서 신청**: Yes24 URL 입력만으로 도서 정보 자동 조회 및 신청
- **자동 정산**: 동호회 지원금(최대 30,000원) 자동 계산, 본인 부담금 확인 및 입금 완료 처리
- **관리자 기능**: 회원 관리, 회비 관리, 신청 현황 조회, 대리 신청, Excel 내보내기
- **자동 마감**: 지정 일시에 자동으로 신청 마감

## 기술 스택

| 구분 | 기술 |
|------|------|
| Framework | Python + Streamlit |
| Database | Google Sheets (gspread) |
| Hosting | 사내 컨테이너 (oauth2-proxy 경유) |
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

시스템 Python이 PEP 668(`externally-managed-environment`)로 보호되는 환경에서는 가상환경을 사용합니다.

```bash
python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
```

### 3. secrets.toml 설정

Streamlit은 **프로젝트 로컬 → 사용자 전역** 순으로 secrets를 찾습니다.

| 위치 | 용도 |
|------|------|
| `~/.streamlit/secrets.toml` | **운영 권장.** 저장소 밖에 있어 브랜치 전환·워크트리 생성에도 자격증명이 유지됩니다. |
| `<프로젝트>/.streamlit/secrets.toml` | 다른 자격증명으로 테스트할 때. 존재하면 전역보다 우선합니다. |

```bash
mkdir -p ~/.streamlit
cp .streamlit/secrets.toml.example ~/.streamlit/secrets.toml
chmod 600 ~/.streamlit/secrets.toml
```

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
- `SCRAPER_API_KEY`(선택): ScrapingBee 우회 키. **사내 컨테이너 호스팅에서는 설정하지 않습니다.**
  키가 없으면 `utils/scraper.py`가 자동으로 Yes24 직접 요청(direct 모드)으로 동작합니다.
  Yes24가 해외 IP를 차단하므로 해외 호스팅에서만 필요했던 값입니다.

### 4. Google Sheets 초기 설정

스프레드시트 내 워크시트(탭)와 헤더를 자동으로 생성하는 스크립트를 실행합니다.

```bash
python scripts/setup_sheets.py
```

이 스크립트는 다음 5개 워크시트를 생성합니다:

| 워크시트 | 헤더 | 설명 |
|----------|------|------|
| Members | `Name`, `PIN`, `Fee_Paid` | 회원 명부 (PIN: 4자리, Fee_Paid: 회비 납부 여부) |
| Orders | `Order_ID`, `Order_Month`, `Name`, `Book_URL`, `Title`, `Author`, `Price`, `Created_At`, `Publisher`, `ISBN` | 주문 내역 |
| Config | `Key`, `Value` | 서비스 설정 (접수월, 마감 여부, 자동마감 일시) |
| Payments | `Name`, `Order_Month`, `Is_Paid`, `Paid_At` | 본인 부담금 입금 상태 |
| Logs | `Timestamp`, `Event_Type`, `Message` | 이벤트 로그 |

### 5. 앱 실행

```bash
scripts/start_server.sh
```

중지는 `scripts/stop_server.sh`, 로그는 `logs/app.log`에서 확인합니다.

로컬에서 프록시 없이 띄워볼 때는 `.streamlit/config.toml`의 `baseUrlPath` 때문에
`http://localhost:8501/bdbd/`로 접속해야 합니다.

## 프로젝트 구조

```
├── app.py                      # Streamlit 메인 앱 (st.navigation 기반, 자동마감 체크)
├── pages/
│   ├── home.py                 # 홈 - 서비스 안내
│   ├── login.py                # 로그인 / 프로필 (PIN 변경)
│   ├── dashboard.py            # 도서 구매 신청 및 정산 조회
│   └── admin.py                # 관리자 (회원/주문/회비 관리, 대리 신청, Excel 내보내기)
├── utils/
│   ├── __init__.py             # 데이터 모델 (BookInfo, Settlement, OrderRecord, MemberRecord, PaymentRecord, ConfigRecord)
│   ├── sheets.py               # Google Sheets CRUD (캐싱, 재시도 포함)
│   ├── scraper.py              # Yes24 도서 정보 스크래핑
│   ├── settlement.py           # 정산 로직 (지원금 계산, 주문별 배분)
│   ├── navigation.py           # 네비게이션 페이지 목록 생성
│   └── sidebar.py              # 사이드바 렌더링 및 session_state 초기화
├── scripts/
│   └── setup_sheets.py         # Google Sheets 초기 설정 스크립트
├── tests/
│   ├── conftest.py             # 테스트 공통 픽스처
│   ├── test_scraper.py         # 스크래퍼 테스트
│   ├── test_settlement.py      # 정산 로직 테스트
│   ├── test_sheets.py          # Sheets CRUD 테스트
│   ├── test_members.py         # 회원 관리(PIN, 회비) 테스트
│   ├── test_navigation.py      # 네비게이션 로직 테스트
│   └── test_integration.py     # 통합 테스트
├── docs/
│   ├── PRD.md                  # 제품 요구사항 정의서
│   └── TRD.md                  # 기술 요구사항 정의서
├── .streamlit/
│   ├── config.toml             # Streamlit 테마/서버 설정 (baseUrlPath, loopback 바인딩)
│   ├── secrets.toml.example    # secrets 템플릿
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

## 배포 (사내 컨테이너)

Yes24가 해외 서버 IP와 프록시 경유 접근을 모두 차단하여, Streamlit Community Cloud에서는
도서 정보 조회가 동작하지 않습니다. 그래서 국내 IP를 쓰는 사내 컨테이너에서 직접 호스팅합니다.

### 구성

```
사용자 → https://fdfwtools.vieworks.com/bdbd/
       → 호스트 nginx → oauth2-proxy (:7000 평문 / :7443 TLS)
       → 이 앱 127.0.0.1:8501/bdbd/
       → Yes24 직접 요청 (국내 IP)
```

- oauth2-proxy는 경로 프리픽스를 **벗기지 않고 그대로 전달**하므로, 이 앱이 직접 `/bdbd/`
  아래에서 서비스합니다. 관련 설정은 `.streamlit/config.toml`의 `baseUrlPath`입니다.
- 프록시를 우회한 직접 접근을 막기 위해 `address = "127.0.0.1"`로 loopback에만 바인딩합니다.

### 배포 절차

1. venv 생성 및 의존성 설치 (위 "2. 의존성 설치")
2. `.streamlit/secrets.toml` 작성 (위 "3. secrets.toml 설정", `SCRAPER_API_KEY` 제외)
3. `scripts/start_server.sh` 실행
4. oauth2-proxy에 라우트 등록 — `/opt/fdfwtools/start.sh`의 `ARGS` 배열에 아래 3줄 추가 후
   oauth2-proxy 재기동 (**root 권한 필요**)

   ```bash
   --upstream="http://127.0.0.1:8501/bdbd"
   --upstream="http://127.0.0.1:8501/bdbd/"
   --skip-auth-route="^/bdbd"
   ```

   **`upstream`이 2줄인 이유**: oauth2-proxy는 경로가 `/`로 끝나면 prefix 매칭,
   아니면 정확 매칭으로 등록합니다. `/bdbd/` 하나만 두면 트레일링 슬래시가 없는
   `/bdbd` 요청이 이 라우트에 걸리지 않고 catch-all(app1)로 흘러가 app1의 404가 뜹니다.
   정확 매칭 라우트를 함께 등록하면 `/bdbd`가 이 앱에 도달해
   `https://fdfwtools.vieworks.com/bdbd/`로 307 리다이렉트됩니다.

   `skip-auth-route`도 같은 이유로 `^/bdbd/`가 아닌 `^/bdbd`여야 합니다.
   (`^/dfpdqa/`로 등록된 기존 라우트는 `/dfpdqa` 접근 시 SSO로 튕깁니다.)

   이 서비스는 SSO를 적용하지 않고 앱 자체의 이름+PIN 인증만 사용합니다.

### 컨테이너 재시작 시

컨테이너에 systemd/cron이 없고 PID 1이 `sleep`이라 자동 기동되지 않습니다.
재시작 후에는 `scripts/start_server.sh`를 다시 실행해야 합니다.

## 테스트

```bash
pytest
```
