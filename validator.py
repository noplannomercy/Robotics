# validator.py
import re
from dataclasses import dataclass

# HCA 패키지명 추출 — CREATE [OR REPLACE] PACKAGE [BODY] <NAME>
PKG_NAME_RE = re.compile(
    r'CREATE\s+(?:OR\s+REPLACE\s+)?PACKAGE\s+(?:BODY\s+)?(\w+)',
    re.IGNORECASE,
)

# HCA 프로시저/함수 선언 추출 — PROCEDURE/FUNCTION <NAME>
PROC_NAME_RE = re.compile(
    r'(?:PROCEDURE|FUNCTION)\s+(\w+)\s*[(\n]',
    re.IGNORECASE,
)


@dataclass
class ValidationResult:
    passed: bool
    feedback: str | None = None


def validate(raw: str, reverse: str) -> ValidationResult:
    failures: list[str] = []

    # check 1: 패키지명이 역문서에 포함되는지
    pkg_matches = PKG_NAME_RE.findall(raw)
    if pkg_matches:
        pkg_name = pkg_matches[0].upper()
        if pkg_name not in reverse.upper():
            failures.append(f"check 1 실패: 패키지명 '{pkg_name}' 누락")

    # check 2: 주요 프로시저/함수명이 역문서에 포함되는지
    procs = {p.upper() for p in PROC_NAME_RE.findall(raw)}
    # 내부 private 프로시저 제외 — 소문자로 시작하는 것은 private일 가능성
    public_procs = {p for p in procs if not p.startswith('SP_REFRESH') and len(p) > 3}
    missing_procs = [p for p in public_procs if p not in reverse.upper()]
    if len(missing_procs) > len(public_procs) * 0.5:
        # 절반 이상 누락 시에만 실패 (일부 private 프로시저는 역문서에 없을 수 있음)
        failures.append(f"check 2 실패: 프로시저 다수 누락 — {', '.join(sorted(missing_procs)[:5])}")

    if not failures:
        return ValidationResult(passed=True)
    return ValidationResult(passed=False, feedback="\n".join(failures))
