---
name: gen-test
description: Python pytest 기반 테스트 코드를 생성합니다. 대상 모듈의 함수/클래스를 분석하여 테스트 케이스를 자동 작성합니다.
disable-model-invocation: true
---

# gen-test

주어진 Python 모듈에 대한 pytest 테스트 코드를 생성합니다.

## 사용법
`/gen-test <파일경로>` 또는 `/gen-test <모듈명>`

## 규칙
1. 테스트 파일은 `tests/` 디렉토리에 `test_<모듈명>.py` 형식으로 생성
2. 각 함수/메서드에 대해 정상 케이스, 경계값, 에러 케이스를 포함
3. Google Sheets API 호출은 mock 처리 (unittest.mock.patch 사용)
4. Yes24 스크래핑 테스트는 fixture로 HTML 샘플 제공
5. 정산 로직은 다양한 금액 시나리오 테스트 (0원, 30000원 경계, 초과 등)
6. 한국어 docstring으로 테스트 의도 명시

## 테스트 구조 예시
```python
import pytest
from unittest.mock import patch, MagicMock

class Test대상클래스:
    """대상클래스 테스트"""

    def test_정상_케이스(self):
        """정상 입력에 대한 기대 결과 검증"""
        pass

    def test_경계값(self):
        """경계값 테스트"""
        pass

    def test_에러_케이스(self):
        """예외 상황 처리 검증"""
        pass
```
