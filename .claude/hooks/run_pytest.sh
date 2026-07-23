#!/usr/bin/env bash
# PostToolBatch 훅: .py 파일 내용이 바뀐 배치 뒤에만 pytest를 실행하고,
# 실패한 경우에만 systemMessage + additionalContext로 결과를 알린다.
# 통과 시에는 조용히 종료(성공 케이스를 매번 노출하지 않기 위함).
#
# PostToolUse는 도구 호출마다 실행되어 한 배치에서 파일을 여러 개 고치면
# 전체 스위트가 중복 실행된다. PostToolBatch는 배치당 1회만 발화하지만,
# 대신 tool_input/file_path가 오지 않고 matcher도 지원하지 않아(모든 배치에서
# 발화) 편집 여부를 훅이 직접 판정해야 한다. 여기서는 .py 파일 내용의 지문을
# 저장해 두고 달라졌을 때만 pytest를 돌린다.
set -u

cd "$CLAUDE_PROJECT_DIR" 2>/dev/null || exit 0

# worktree에서는 .git이 파일이므로 rev-parse로 실제 git 디렉터리를 얻는다
# (worktree마다 별도 경로가 나오므로 지문도 자연스럽게 분리된다)
GIT_DIR=$(git rev-parse --git-dir 2>/dev/null) || exit 0
STATE_FILE="$GIT_DIR/claude-pytest-fingerprint"

# 추적 중이거나 미추적(비무시)인 .py 파일 전체 내용의 지문
CURRENT=$(git ls-files -zco --exclude-standard -- '*.py' \
  | xargs -0 -r sha1sum 2>/dev/null \
  | sha1sum \
  | cut -d' ' -f1)
[ -z "$CURRENT" ] && exit 0

PREV=$(cat "$STATE_FILE" 2>/dev/null || true)
printf '%s' "$CURRENT" > "$STATE_FILE"

# 지문이 같으면 .py 변경이 없었던 배치이므로 건너뛴다
[ "$CURRENT" = "$PREV" ] && exit 0
# 이전 지문이 없으면 기준선만 남기고 건너뛴다(최초 실행)
[ -z "$PREV" ] && exit 0

OUT=$(python -m pytest -q 2>&1)
CODE=$?

if [ "$CODE" -eq 0 ]; then
  exit 0
fi

# 실패 요약은 argv 길이 제한을 피해 표준 입력으로 전달한다
printf '%s\n' "$OUT" | tail -20 | python -c '
import json
import sys

summary = sys.stdin.read()
print(json.dumps({
    "systemMessage": "pytest 실패 감지 — 방금 변경과 관련된 코드/테스트를 확인하세요.",
    "hookSpecificOutput": {
        "hookEventName": "PostToolBatch",
        "additionalContext": "PostToolBatch pytest 자동 실행 결과 실패:\n" + summary,
    },
}))
'
exit 0
