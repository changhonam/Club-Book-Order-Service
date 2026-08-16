# 독서동호회 도서 구매 신청 서비스

## 프로젝트 개요
독서동호회 회원들이 Yes24 도서 링크로 구매 신청하고, 본인 부담금을 확인하며, 관리자가 일괄 구매를 진행하는 사내 웹 서비스.

## 기술 스택
- **Framework**: Python + Streamlit
- **Hosting**: 사내 컨테이너 (127.0.0.1:8501, oauth2-proxy 경유 `https://fdfwtools.vieworks.com/bdbd/`)
- **Database**: Google Sheets API (gspread, pandas)
- **Scraping**: requests + BeautifulSoup4
- **Export**: openpyxl (Excel)

## 개발 규칙
- 코드 포맷팅: ruff (자동 hook 적용됨)
- 테스트: pytest
- 언어: 코드(영문), UI/주석(한국어)
- secrets.toml은 절대 커밋하지 않을 것
- Plan 기반 작업 완료 시 `/update-docs`를 실행하여 문서 동기화 확인할 것 (단순 수정은 생략 가능)
- **시트 스키마 변경 시 반드시 `scripts/setup_sheets.py`도 함께 업데이트할 것**: 신규 시트 추가, 컬럼 추가/변경/삭제가 발생하면 해당 시트의 생성 로직과 기존 시트 마이그레이션 로직을 모두 반영해야 함

## 프로젝트 구조
```
├── app.py                  # Streamlit 메인 앱 (st.navigation 기반)
├── pages/
│   ├── home.py             # 홈 - 서비스 안내
│   ├── login.py            # 로그인 / 프로필 (PIN 변경)
│   ├── dashboard.py        # 도서 구매 신청 및 현황 조회
│   └── admin.py            # 관리자 (회원/주문/회비 관리, 대리 신청, Excel)
├── utils/
│   ├── __init__.py         # 데이터 모델
│   ├── sheets.py           # Google Sheets CRUD
│   ├── scraper.py          # Yes24 스크래핑
│   ├── settlement.py       # 정산 로직
│   ├── bank_parser.py      # 하나은행 거래내역 엑셀 파싱 및 회원 매칭
│   ├── navigation.py       # 네비게이션 페이지 목록 생성
│   └── sidebar.py          # 사이드바 및 session_state 초기화
├── scripts/
│   ├── setup_sheets.py     # Google Sheets 초기 설정 및 마이그레이션 스크립트
│   ├── start_server.sh     # 서버 기동 (nohup + 헬스체크)
│   └── stop_server.sh      # 서버 중지
├── requirements.txt
├── .streamlit/
│   ├── config.toml         # baseUrlPath="bdbd", loopback 바인딩
│   ├── secrets.toml.example
│   └── secrets.toml        # (gitignore 대상)
└── tests/
```

## 호스팅 구조
- Yes24가 해외 IP·프록시를 차단하여 Streamlit Community Cloud에서 사내 컨테이너로 이전함
- 요청 경로: 호스트 nginx → oauth2-proxy(`/opt/fdfwtools/start.sh`, root 소유) → `127.0.0.1:8501/bdbd/`
- **oauth2-proxy는 경로 프리픽스를 벗기지 않는다** → `baseUrlPath = "bdbd"` 필수
- oauth2-proxy는 upstream 경로가 `/`로 끝나면 prefix 매칭, 아니면 정확 매칭으로 등록한다.
  그래서 `--upstream`을 `/bdbd`와 `/bdbd/` **두 줄** 등록해야 트레일링 슬래시 없는
  `/bdbd` 요청이 catch-all(app1)로 새지 않는다. `--skip-auth-route`도 `^/bdbd`(슬래시 없이)
- 이 경로는 SSO를 걸지 않음 (앱 자체 이름+PIN 인증만 사용)
- `SCRAPER_API_KEY`(ScrapingBee)를 설정하지 않으면 `utils/scraper.py`가 자동으로 direct 모드로 동작함. 사내 호스팅에서는 설정하지 말 것
- systemd/cron 없음(PID 1이 `sleep`) → 컨테이너 재시작 시 `scripts/start_server.sh` 수동 실행 필요
- 의존성은 venv 사용 (시스템 Python은 PEP 668로 보호됨), Python 3.14 환경이라 `pandas<3` 고정
- **secrets는 `~/.streamlit/secrets.toml`(전역)에 둔다.** 저장소 밖이라 브랜치 전환·워크트리
  생성에도 유지된다. Streamlit은 프로젝트 로컬을 먼저 보고 없으면 전역을 읽으므로,
  다른 자격증명으로 테스트할 때만 프로젝트에 `.streamlit/secrets.toml`을 둔다.
  `scripts/setup_sheets.py`도 같은 순서로 탐색한다
- 운영은 메인 저장소 디렉터리(`main` 브랜치)에서 실행하고, 개발은 워크트리에서 한다

## 핵심 비즈니스 로직
- 정산: 동호회 지원금 = floor(min(월 총액 / 2, 30000)), 본인 부담 = 총액 - 지원금
- 인증: 이름 + PIN(4자리) 로그인 (Members 시트 검증), 관리자는 추가 비밀번호
- 마감: 접속 시 auto_close_datetime 체크 방식 (cron 미사용)
