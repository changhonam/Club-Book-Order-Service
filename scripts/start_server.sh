#!/bin/bash
# 독서동호회 도서 구매 신청 서비스 기동 스크립트
#
#   사용자 → https://fdfwtools.vieworks.com/bdbd/
#          → 호스트 nginx → oauth2-proxy(:7000/:7443, /opt/fdfwtools/start.sh)
#          → 이 앱 127.0.0.1:8501/bdbd/
#
# oauth2-proxy는 경로 프리픽스를 벗기지 않고 그대로 넘기므로, 이 앱이 직접
# /bdbd/ 아래에서 서비스해야 한다. 해당 설정은 .streamlit/config.toml의
# baseUrlPath에 있다(포트·바인딩 주소도 같은 파일에서 관리).
#
# /opt/fdfwtools/stop.sh는 oauth2-proxy와 app1/app2만 정리하므로, 이 프로세스는
# dfpdqa와 마찬가지로 SSO 스택 재기동과 무관하게 살아남는다.
#
# 사용법:  scripts/start_server.sh
# 중지:    scripts/stop_server.sh

set -u
cd "$(dirname "$0")/.." || exit 1
PROJECT_DIR=$(pwd)

VENV="$PROJECT_DIR/.venv"
LOG_DIR="$PROJECT_DIR/logs"
LOG="$LOG_DIR/app.log"

if [ ! -x "$VENV/bin/streamlit" ]; then
  echo "❌ venv가 없다. 먼저 아래를 실행할 것:"
  echo "   python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt"
  exit 1
fi

# Streamlit은 프로젝트 로컬을 먼저, 없으면 사용자 전역 secrets를 읽는다.
# 운영에서는 전역에 두어 브랜치·워크트리를 옮겨도 자격증명이 유지되게 한다.
if [ -f "$PROJECT_DIR/.streamlit/secrets.toml" ]; then
  echo "  secrets: $PROJECT_DIR/.streamlit/secrets.toml (로컬)"
elif [ -f "$HOME/.streamlit/secrets.toml" ]; then
  echo "  secrets: $HOME/.streamlit/secrets.toml (전역)"
else
  echo "❌ secrets.toml이 없다. 아래 중 한 곳에 두고 다시 실행할 것:"
  echo "   $PROJECT_DIR/.streamlit/secrets.toml"
  echo "   $HOME/.streamlit/secrets.toml   ← 운영 권장(브랜치 전환에 영향 없음)"
  echo "   ※ 사내 호스팅에서는 SCRAPER_API_KEY를 넣지 않는다(Yes24 직접 요청)."
  exit 1
fi

mkdir -p "$LOG_DIR"

echo "=== 기존 프로세스 정리 ==="
"$PROJECT_DIR/scripts/stop_server.sh"

# stop_server.sh는 이 체크아웃에서 띄운 프로세스만 정리한다. 다른 체크아웃(워크트리 등)이
# 8501을 잡고 있으면 아래 헬스체크가 그쪽 인스턴스에 응답받아 거짓 성공이 나므로 먼저 막는다.
if timeout 2 bash -c "echo > /dev/tcp/127.0.0.1/8501" 2>/dev/null; then
  echo "❌ 8501 포트를 다른 프로세스가 이미 사용 중이다:"
  pgrep -af "streamlit run" | grep -v "^$$ " | sed 's/^/   /'
  echo "   해당 체크아웃에서 scripts/stop_server.sh를 실행한 뒤 다시 시도할 것."
  exit 1
fi

echo "=== 앱 기동 ==="
# app.py가 utils 로거를 INFO로 올려두어 [scraper] 진단 로그가 이 파일에 쌓인다.
nohup "$VENV/bin/streamlit" run app.py >> "$LOG" 2>&1 &
sleep 3

# config.toml의 baseUrlPath와 일치해야 한다
HEALTH="http://127.0.0.1:8501/bdbd/_stcore/health"
if curl -sf --max-time 5 "$HEALTH" > /dev/null; then
  echo "  ✅ 기동됨 → https://fdfwtools.vieworks.com/bdbd/"
  echo "  로그: $LOG"
else
  echo "  ❌ 헬스체크 실패 ($HEALTH). 로그 확인: $LOG"
  tail -20 "$LOG"
  exit 1
fi
