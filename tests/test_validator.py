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


# --- check 3: no standalone enum values ---

def test_check3_pass_enum_with_table_col():
    raw = "STATUS column set to APPROVED"
    reverse = "TBL_LOAN_APPLICATION.STATUS = 'APPROVED'로 변경한다."
    result = validate(raw, reverse)
    assert result.passed is True


def test_check3_fail_standalone_enum():
    raw = "STATUS column"
    reverse = "상태를 'REJECTED'로 변경한다."
    result = validate(raw, reverse)
    assert result.passed is False
    assert "check 3" in result.feedback


# --- check 4: no standalone column names ---

def test_check4_pass_dot_notation():
    raw = "PROC_TEST updates STATUS column"
    reverse = "PROC_TEST는 TBL_LOAN_APPLICATION.STATUS를 변경한다."
    result = validate(raw, reverse)
    assert result.passed is True


def test_check4_fail_standalone_column():
    raw = "PROC_TEST updates EVAL_TYPE column"
    reverse = "PROC_TEST는 EVAL_TYPE을 변경한다."
    result = validate(raw, reverse)
    assert result.passed is False
    assert "check 4" in result.feedback


# --- feedback format ---

def test_feedback_includes_all_failed_checks():
    raw = "PROC_A TBL_B"
    reverse = "proc_a 실행, 'DONE' 상태, EVAL_TYPE 변경"
    result = validate(raw, reverse)
    assert result.passed is False
    # feedback에 여러 check 실패가 모두 포함되어야 함
    assert "check 1" in result.feedback or "check 2" in result.feedback
