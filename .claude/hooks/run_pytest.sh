#!/usr/bin/env bash
# PostToolUse(Edit|Write) 훅: 변경 파일이 .py이면 pytest를 실행하고,
# 실패한 경우에만 systemMessage + additionalContext로 결과를 알린다.
# 통과 시에는 조용히 종료(성공 케이스를 매번 노출하지 않기 위함).
set -u

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | python -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('file_path','') or d.get('tool_response',{}).get('filePath',''))" 2>/dev/null)

case "$FILE_PATH" in
  *.py) ;;
  *) exit 0 ;;
esac

cd "$CLAUDE_PROJECT_DIR" || exit 0
OUT=$(python -m pytest -q 2>&1)
CODE=$?

if [ "$CODE" -eq 0 ]; then
  exit 0
fi

SUMMARY=$(echo "$OUT" | tail -20)
python - "$SUMMARY" <<'PYEOF'
import json
import sys

summary = sys.argv[1]
print(json.dumps({
    "systemMessage": "pytest 실패 감지 — 방금 변경과 관련된 코드/테스트를 확인하세요.",
    "hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": "PostToolUse pytest 자동 실행 결과 실패:\n" + summary,
    },
}))
PYEOF
exit 0
