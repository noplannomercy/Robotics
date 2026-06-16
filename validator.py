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
    r'(?:PROCEDURE|FUNCTION)\s+(\w+)',
    re.IGNORECASE,
)

# HCA 명명 규칙상 프로시저/함수 식별자 — PROC_* / FUNC_* / FN_* 접두 (대문자 표준 표기)
PROC_IDENT_RE = re.compile(r'\b((?:PROC|FUNC|FN)_[A-Z0-9_]+)\b')

# PACKAGE BODY 시작 지점 — 스펙(HEADER)과 본문(BODY)을 분리하기 위한 기준
PKG_BODY_RE = re.compile(
    r'CREATE\s+(?:OR\s+REPLACE\s+)?PACKAGE\s+BODY\s+\w+',
    re.IGNORECASE,
)


def _public_procs(raw: str) -> set[str]:
    """public 프로시저/함수 집합을 정확히 산정한다.

    B3: SP_REFRESH 단일 접두 과대제외를 폐지하고, PACKAGE 스펙(HEADER)에
    선언된 프로시저만 public 으로 간주한다. private 판별 기준은 '소문자 가정'이
    아니라 'HEADER 선언 여부'다.
    """
    body_match = PKG_BODY_RE.search(raw)
    if body_match:
        # 스펙(HEADER) = PACKAGE BODY 이전 구간. 여기 선언된 것만 public.
        header = raw[: body_match.start()]
    else:
        # PACKAGE BODY 가 없으면 HEADER/BODY 분리가 불가능한 원문(예: 단일
        # 프로시저 소스, 또는 스펙만). 전체를 선언 구간으로 본다.
        header = raw

    procs = {p.upper() for p in PROC_NAME_RE.findall(header)}
    procs |= {p.upper() for p in PROC_IDENT_RE.findall(header)}
    return procs


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

    # check 2: 주요 프로시저/함수명이 역문서에 표준(대문자) 표기로 포함되는지
    # B3: public 분모는 HEADER 선언 기준으로 정확히 산정한다.
    public_procs = {p for p in _public_procs(raw) if len(p) > 3}
    # 표준 표기(대문자)로 그대로 나타나야 한다 — 소문자 표기는 누락으로 간주.
    missing_procs = [p for p in public_procs if p not in reverse]
    # B1: 50% 임계 제거 — public 프로시저가 단 하나라도 누락되면 즉시 실패.
    if missing_procs:
        failures.append(f"check 2 실패: 프로시저 누락 — {', '.join(sorted(missing_procs)[:5])}")

    if not failures:
        return ValidationResult(passed=True)
    return ValidationResult(passed=False, feedback="\n".join(failures))
