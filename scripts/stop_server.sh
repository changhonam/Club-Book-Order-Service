#!/bin/bash
# 독서동호회 도서 구매 신청 서비스 중지 스크립트
#
# 이 프로젝트의 venv로 띄운 streamlit만 정리한다. 컨테이너에는 다른 서비스도
# 함께 돌고 있으므로(app1/app2/dfpdqa) 패턴을 이 프로젝트 경로로 한정한다.

set -u
cd "$(dirname "$0")/.." || exit 1
PROJECT_DIR=$(pwd)

PATTERN="$PROJECT_DIR/.venv/bin/streamlit"

PIDS=$(pgrep -f "$PATTERN" || true)
if [ -z "$PIDS" ]; then
  echo "  실행 중인 프로세스 없음"
  exit 0
fi

echo "$PIDS" | while read -r p; do kill "$p" 2>/dev/null; done
sleep 2

# 아직 살아있으면 강제 종료
REMAIN=$(pgrep -f "$PATTERN" || true)
if [ -n "$REMAIN" ]; then
  echo "$REMAIN" | while read -r p; do kill -9 "$p" 2>/dev/null; done
  sleep 1
fi

echo "  중지 완료"
