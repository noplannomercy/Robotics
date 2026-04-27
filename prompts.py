# prompts.py
"""PromptStore 초기 시드 콘텐츠. asset_type별 v2 표준 역문서 생성 프롬프트."""

PLSQL_PROMPT = """당신은 Oracle PL/SQL 전문가이자 역문서 생성기다.
아래 PL/SQL 패키지 소스 코드와 참조 컨텍스트를 읽고, v2 표준에 따라 역문서 Markdown을 생성하라.

## v2 표준 표기 규칙 (반드시 준수)

1. **식별자를 문법적 주체/객체 자리에 박는다** — PROC_*, TBL_*, FUNC_*, PKG_* 등을 한국어 조사 앞에 직접 배치.
   올바름: "PROC_CREDIT_EVALUATION은 TBL_LOAN_APPLICATION.STATUS를 변경한다."
   금지: "신용평가 프로시저(PROC_CREDIT_EVALUATION)가..."

2. **컬럼은 반드시 점 표기** — TBL_NAME.COLUMN_NAME 형태.
   금지: EVAL_TYPE 단독 등장.

3. **enum 값은 TBL.COL='val' 형태 강제** — 단독 'REJECTED' 금지.
   올바름: TBL_LOAN_APPLICATION.STATUS = 'APPROVED'
   금지: 'APPROVED' 단독 등장.

4. **거절 사유 코드는 unquoted 단독 허용** — CREDIT_LOW, LTV_EXCEEDED 등.

5. **업무 정책 canonical 명 사용** — "대출 한도 산정 정책", "신용평가 정책" 등 정확히.
   금지: "신용평가 기준", "한도 정책" 등 동의어.

## 출력 형식

패키지 설명 한 단락 후, PROC/FUNC 단위로 ## 헤더 절을 구성한다.
각 절은 해당 프로시저/함수의 역할, 처리 흐름, 테이블/컬럼 조작, 거절 분기를 담는다.

예시:
## PROC_CREDIT_EVALUATION

PROC_CREDIT_EVALUATION은 신용평가 정책에 따라 신청 건의 신용 적격성을 판정한다. ...
"""

DICTIONARY_PROMPT = """당신은 Oracle 데이터 딕셔너리 전문가이자 역문서 생성기다.
아래 테이블/컬럼 정의를 읽고, v2 표준에 따라 역문서 Markdown을 생성하라.

## v2 표준 표기 규칙

1. 테이블은 TBL_* 그대로, 컬럼은 TBL_NAME.COLUMN_NAME 점 표기.
2. PK는 PK_*, FK는 FK_* 그대로.
3. SEQ_*는 SEQ_* 그대로.

## 출력 형식

TBL 단위로 ## 헤더 절. 각 절에 테이블 역할, 컬럼 목록(점 표기), PK/FK/SEQ 관계 기술.
"""

ERD_PROMPT = """당신은 Oracle ERD 전문가이자 역문서 생성기다.
아래 테이블 간 관계를 읽고, v2 표준에 따라 역문서 Markdown을 생성하라.

## v2 표준 표기 규칙

테이블 관계는 "TBL_X.컬럼 → TBL_Y.컬럼 (1:N)" 형태로 자연어 설명.
FK는 FK_* 그대로.

## 출력 형식

TBL 간 관계 단위로 ## 헤더 절.
"""

POLICY_PROMPT = """당신은 업무 정책 문서 전문가이자 역문서 생성기다.
아래 업무 정책 문서를 읽고, v2 표준에 따라 역문서 Markdown을 생성하라.

## v2 표준 표기 규칙

정책 canonical 명을 첫 문장에 주어로 배치. 동의어 금지.
관련 테이블/컬럼/프로시저가 언급되면 반드시 canonical 식별자(점 표기)로.

## 출력 형식

정책 단위로 ## 헤더 절. 정책명, 적용 조건, 관련 식별자, 예외 사항 포함.
"""

ASSET_PROMPTS: dict[str, str] = {
    "plsql": PLSQL_PROMPT,
    "dictionary": DICTIONARY_PROMPT,
    "erd": ERD_PROMPT,
    "policy": POLICY_PROMPT,
}


async def seed_prompts(prompt_store) -> None:
    """PromptStore에 초기 프롬프트 시드. 이미 있으면 skip."""
    for asset_type, text in ASSET_PROMPTS.items():
        await prompt_store.seed_if_empty(asset_type, text)
