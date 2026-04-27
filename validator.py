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

    # check 3: enum 값 단독 등장 금지 (TBL.COL='val' 형태 강제)
    # PROC_*/FUNC_*/PKG_* 호출 인자로 사용된 문자열 상수는 거절/알림 코드이므로 제외
    proc_call_args: set[str] = set()
    for line in raw.split('\n'):
        if re.search(r'\b(?:PROC|FUNC|PKG)_[A-Z0-9_]+\s*\(', line, re.IGNORECASE):
            proc_call_args.update(re.findall(r"'([A-Z][A-Z0-9_]+)'", line))
    all_quoted = re.findall(r"'([A-Z][A-Z0-9_]+)'", reverse)
    eq_preceded = re.findall(r"=\s*'([A-Z][A-Z0-9_]+)'", reverse)
    standalone_enums = [e for e in all_quoted if e not in eq_preceded and e not in proc_call_args]
    if standalone_enums:
        failures.append(
            f"check 3 실패: enum 단독 등장 — {', '.join(standalone_enums[:5])}. "
            "반드시 TBL.COL='val' 형태 사용"
        )

    # check 4: 컬럼명 단독 등장 금지 (점 표기 강제)
    # source에서 따옴표로 등장한 값은 거절 사유 코드/상수이므로 역문서에서 단독 허용
    source_quoted_vals = set(re.findall(r"'([A-Z][A-Z0-9_]+)'", raw))
    standalone_cols = STANDALONE_COL_RE.findall(reverse)
    non_prefixed = [
        c for c in standalone_cols
        if not re.match(r'^(?:TBL|PROC|FUNC|PKG|SEQ|FK|PK)_', c)
        and c not in rev_ids
        and not re.search(rf'\.{re.escape(c)}(?![A-Z0-9_])', reverse)
        and c not in source_quoted_vals
    ]
    if non_prefixed:
        failures.append(
            f"check 4 실패: 컬럼명 단독 등장 — {', '.join(non_prefixed[:5])}. "
            "반드시 TBL_NAME.COLUMN_NAME 형태 사용"
        )

    if not failures:
        return ValidationResult(passed=True)
    return ValidationResult(passed=False, feedback="\n".join(failures))
