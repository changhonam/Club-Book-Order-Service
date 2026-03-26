# 독서동호회 도서 구매 신청 서비스

## 프로젝트 개요
독서동호회 회원들이 Yes24 도서 링크로 구매 신청하고, 본인 부담금을 확인하며, 관리자가 일괄 구매를 진행하는 사내 웹 서비스.

## 기술 스택
- **Framework**: Python + Streamlit
- **Hosting**: Streamlit Community Cloud
- **Database**: Google Sheets API (gspread, pandas)
- **Scraping**: requests + BeautifulSoup4
- **Export**: openpyxl (Excel)

## 개발 규칙
- 코드 포맷팅: ruff (자동 hook 적용됨)
- 테스트: pytest
- 언어: 코드(영문), UI/주석(한국어)
- secrets.toml은 절대 커밋하지 않을 것

## 프로젝트 구조
```
├── app.py                  # Streamlit 메인 앱
├── pages/                  # Streamlit 멀티페이지
├── utils/                  # 유틸리티 모듈
│   ├── sheets.py           # Google Sheets CRUD
│   ├── scraper.py          # Yes24 스크래핑
│   └── settlement.py       # 정산 로직
├── requirements.txt
├── .streamlit/
│   ├── config.toml
│   └── secrets.toml        # (gitignore 대상)
└── tests/
```

## 핵심 비즈니스 로직
- 정산: 동호회 지원금 = floor(min(월 총액 / 2, 30000)), 본인 부담 = 총액 - 지원금
- 인증: 이름 기반 심플 로그인 (Members 시트 검증), 관리자는 추가 비밀번호
- 마감: 접속 시 auto_close_datetime 체크 방식 (cron 미사용)
