# tests/test_validator.py
import pytest
from validator import validate, ValidationResult

# --- check 1: project identifier coverage ---

def test_check1_pass_all_identifiers_present():
    raw = "PROC_CREDIT_EVALUATION calls TBL_LOAN_APPLICATION"
    reverse = "PROC_CREDIT_EVALUATION은 TBL_LOAN_APPLICATION을 조회한다."
    result = validate(raw, reverse)
    assert result.passed is True


def test_check1_fail_missing_identifier():
    raw = "PROC_CREDIT_EVALUATION calls TBL_LOAN_APPLICATION and TBL_CREDIT_SCORE"
    reverse = "PROC_CREDIT_EVALUATION은 TBL_LOAN_APPLICATION을 조회한다."
    result = validate(raw, reverse)
    assert result.passed is False
    assert "TBL_CREDIT_SCORE" in result.feedback
    assert "check 1" in result.feedback


def test_check1_sql_keywords_excluded():
    # BEGIN, END, IF, EXCEPTION 등 SQL 키워드는 check 1에서 제외
    raw = "BEGIN IF x THEN END IF; EXCEPTION WHEN OTHERS"
    reverse = "이 프로시저는 조건 분기를 수행한다."
    result = validate(raw, reverse)
    assert result.passed is True  # SQL 키워드 누락으로 실패하면 안 됨


# --- check 2: canonical notation ---

def test_check2_pass_all_uppercase():
    raw = "PROC_TEST calls TBL_MASTER"
    reverse = "PROC_TEST는 TBL_MASTER를 조회한다."
    result = validate(raw, reverse)
    assert result.passed is True


def test_check2_fail_lowercase_identifier():
    raw = "PROC_TEST"
    reverse = "proc_test는 실행된다."
    result = validate(raw, reverse)
    assert result.passed is False
    assert "check 2" in result.feedback


# --- B1: 0% 임계 — 프로시저 1개만 누락돼도 즉시 실패 ---

def test_b1_single_missing_public_proc_fails():
    # public 프로시저 2개 중 단 1개만 누락돼도 (50% 미만) 즉시 실패해야 한다.
    raw = (
        "PROCEDURE PROC_ALPHA IS BEGIN NULL; END;\n"
        "PROCEDURE PROC_BETA IS BEGIN NULL; END;"
    )
    reverse = "PROC_ALPHA는 실행된다."  # PROC_BETA 누락 (1/2 = 50%, 0% 임계여야 fail)
    result = validate(raw, reverse)
    assert result.passed is False
    assert "check 2" in result.feedback
    assert "PROC_BETA" in result.feedback


def test_b1_all_public_procs_present_passes():
    raw = (
        "PROCEDURE PROC_ALPHA IS BEGIN NULL; END;\n"
        "PROCEDURE PROC_BETA IS BEGIN NULL; END;"
    )
    reverse = "PROC_ALPHA와 PROC_BETA를 모두 설명한다."
    result = validate(raw, reverse)
    assert result.passed is True


# --- B3: HEADER 선언 기준 public 판별 (분모 정확화) ---

def test_b3_sp_refresh_proc_not_overexcluded():
    # SP_REFRESH 접두 프로시저도 선언돼 있으면 public — 과대제외 금지.
    # 누락 시 fail 해야 한다 (구버전은 SP_REFRESH* 를 분모에서 빼버려 통과시킴).
    raw = "PROCEDURE SP_REFRESH_CACHE IS BEGIN NULL; END;"
    reverse = "이 패키지는 캐시를 갱신한다."  # SP_REFRESH_CACHE 누락
    result = validate(raw, reverse)
    assert result.passed is False
    assert "SP_REFRESH_CACHE" in result.feedback


def test_b3_body_only_proc_is_private_not_required():
    # HEADER(스펙)에 없고 BODY 안에만 있는 프로시저는 private → 분모에서 제외.
    # 역문서에 없어도 실패하면 안 된다.
    raw = (
        "CREATE OR REPLACE PACKAGE PKG_LOAN AS\n"
        "  PROCEDURE PROC_PUBLIC_API;\n"
        "END PKG_LOAN;\n"
        "CREATE OR REPLACE PACKAGE BODY PKG_LOAN AS\n"
        "  PROCEDURE PROC_INTERNAL_HELPER IS BEGIN NULL; END;\n"
        "  PROCEDURE PROC_PUBLIC_API IS BEGIN NULL; END;\n"
        "END PKG_LOAN;"
    )
    # public(PROC_PUBLIC_API)만 언급, private helper 는 언급 안 함.
    reverse = "PKG_LOAN의 PROC_PUBLIC_API는 외부에 노출되는 API다."
    result = validate(raw, reverse)
    assert result.passed is True


def test_b3_header_declared_public_proc_missing_fails():
    # HEADER 에 선언된 public 프로시저가 역문서에서 누락되면 실패해야 한다.
    raw = (
        "CREATE OR REPLACE PACKAGE PKG_LOAN AS\n"
        "  PROCEDURE PROC_PUBLIC_API;\n"
        "END PKG_LOAN;\n"
        "CREATE OR REPLACE PACKAGE BODY PKG_LOAN AS\n"
        "  PROCEDURE PROC_PUBLIC_API IS BEGIN NULL; END;\n"
        "END PKG_LOAN;"
    )
    reverse = "PKG_LOAN 패키지에 대한 설명."  # PROC_PUBLIC_API 누락
    result = validate(raw, reverse)
    assert result.passed is False
    assert "PROC_PUBLIC_API" in result.feedback


# --- check 3: no standalone enum values ---

def test_check3_pass_enum_with_table_col():
    raw = "STATUS column set to APPROVED"
    reverse = "TBL_LOAN_APPLICATION.STATUS = 'APPROVED'로 변경한다."
    result = validate(raw, reverse)
    assert result.passed is True


def test_check3_removed_passes():
    raw = "STATUS column"
    reverse = "상태를 'REJECTED'로 변경한다."
    result = validate(raw, reverse)
    assert result.passed is True  # check 3 제거됨


# --- check 4 제거됨 ---

def test_check4_removed_passes():
    raw = "PROC_TEST updates EVAL_TYPE column"
    reverse = "PROC_TEST는 EVAL_TYPE을 변경한다."
    result = validate(raw, reverse)
    assert result.passed is True  # check 4 제거됨


# --- feedback format ---

def test_feedback_includes_all_failed_checks():
    raw = "PROC_A TBL_B"
    reverse = "proc_a 실행, 'DONE' 상태, EVAL_TYPE 변경"
    result = validate(raw, reverse)
    assert result.passed is False
    # feedback에 여러 check 실패가 모두 포함되어야 함
    assert "check 1" in result.feedback or "check 2" in result.feedback
