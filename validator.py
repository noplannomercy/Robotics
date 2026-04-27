# validator.py
import re
from dataclasses import dataclass

# 프로젝트 식별자 패턴 — SQL 키워드(BEGIN/END/IF 등) 제외
# \b 대신 ASCII 경계 사용: 한글 등 멀티바이트 문자가 \b를 깨뜨리는 문제 방지
PROJECT_ID_RE = re.compile(r'(?<![A-Z0-9_])(?:TBL|PROC|FUNC|PKG|SEQ|FK|PK)_[A-Z0-9_]+(?![A-Z0-9_])')

# 소문자 식별자 탐지 (check 2) — ASCII 문자만으로 경계 처리
LOWER_ID_RE = re.compile(r'(?<![a-zA-Z0-9_])(?:tbl|proc|func|pkg|seq|fk|pk)_[a-zA-Z0-9_]+', re.IGNORECASE)

# 단독 컬럼명 패턴 (check 4): 점 표기 없이 등장하는 multi-word 대문자 식별자
# \s 제외하지 않음 — 한글/공백 뒤 식별자 모두 포착
STANDALONE_COL_RE = re.compile(r"(?<![A-Z0-9_.])([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)(?![A-Z0-9_=('\\)])")


@dataclass
class ValidationResult:
    passed: bool
    feedback: str | None = None


def validate(raw: str, reverse: str) -> ValidationResult:
    failures: list[str] = []

    # check 1: 프로젝트 식별자 누락 검사
    raw_ids = set(PROJECT_ID_RE.findall(raw))
    rev_ids = set(PROJECT_ID_RE.findall(reverse))
    missing = raw_ids - rev_ids
    if missing:
        failures.append(f"check 1 실패: 다음 식별자 누락 — {', '.join(sorted(missing))}")

    # check 2: canonical 표기 (대문자 underscore 강제)
    lower_ids = LOWER_ID_RE.findall(reverse)
    bad_case = [x for x in lower_ids if x != x.upper()]
    if bad_case:
        failures.append(f"check 2 실패: 소문자 식별자 발견 — {', '.join(bad_case[:5])}")


    if not failures:
        return ValidationResult(passed=True)
    return ValidationResult(passed=False, feedback="\n".join(failures))
