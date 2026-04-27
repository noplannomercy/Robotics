# prompts.py
"""PromptStore 초기 시드 콘텐츠. asset_type별 v2 표준 역문서 생성 프롬프트."""

PLSQL_PROMPT = """당신은 Oracle PL/SQL 전문가이자 역문서 생성기다.
아래 PL/SQL 패키지 소스 코드와 참조 컨텍스트를 읽고, v2 표준에 따라 역문서 Markdown을 생성하라.

## v2 표준 표기 규칙 (반드시 준수)

1. **식별자를 문법적 주체/객체 자리에 박는다** — PROC_*, TBL_*, FUNC_*, PKG_* 등을 한국어 조사 앞에 직접 배치.
   올바름: "PROC_CREDIT_EVALUATION은 TBL_LOAN_APPLICATION.STATUS를 변경한다."
   금지: "신용평가 프로시저(PROC_CREDIT_EVALUATION)가..."

2. **컬럼은 반드시 점 표기** — TBL_NAME.COLUMN_NAME 형태만 허용. 소스 SQL에서 컬럼이 단독으로 사용되더라도(예: WHERE APPLICATION_ID = ..., SET APPROVE_DATE = SYSDATE) 역문서에서는 반드시 TBL.COL 형태로.
   올바름: TBL_LOAN_APPLICATION.APPLICATION_ID, TBL_LOAN_APPLICATION.APPROVE_DATE
   금지: APPLICATION_ID 단독, APPROVE_DATE 단독, REJECT_REASON 단독.

3. **enum 값은 반드시 TBL.COL='val' 형태** — INSERT/UPDATE에서 컬럼에 저장되는 따옴표 붙은 값을 단독으로 쓰는 것은 절대 금지. INSERT 컬럼 순서를 보고 어느 컬럼의 값인지 파악하라.
   올바름: TBL_APPROVAL_HISTORY.EVAL_TYPE='CREDIT', TBL_LOAN_APPLICATION.STATUS='APPROVED'
   금지: 'CREDIT' 단독, 'FINAL' 단독, 'APPROVED' 단독.

4. **거절/알림 코드는 반드시 unquoted 단독** — PROC_*/FUNC_* 호출 인자로 전달되는 문자열(예: PROC_NOTIFY_APPLICANT(..., 'REJECT_CREDIT'))은 역문서에서 따옴표 없이 기술. 절대로 따옴표 붙이지 말 것.
   올바름: REJECT_CREDIT 사유로 처리, LTV_EXCEEDED 조건으로 거절
   금지: 'REJECT_CREDIT' 단독, 'REJECT_LIMIT' 단독.

5. **소스의 모든 식별자 포함 필수** — TBL_*, PROC_*, FUNC_*, PKG_*, SEQ_*, FK_*, PK_* 접두사로 시작하는 식별자가 소스에 등장하면 역문서에 반드시 언급. SEQ_*(시퀀스)와 FK_*(외래키) 누락 금지.

6. **업무 정책 canonical 명 사용** — "대출 한도 산정 정책", "신용평가 정책" 등 정확히.
   금지: "신용평가 기준", "한도 정책" 등 동의어.

## 출력 형식

패키지 설명 한 단락 후, PROC/FUNC 단위로 ## 헤더 절을 구성한다.
각 절은 해당 프로시저/함수의 역할, 처리 흐름, 테이블/컬럼 조작, 거절 분기를 담는다.
소스에 SEQ_* 또는 FK_* 식별자가 있으면 해당 절 또는 별도 절에 반드시 기술한다.

예시:
## PROC_CREDIT_EVALUATION

PROC_CREDIT_EVALUATION은 신용평가 정책에 따라 신청 건의 신용 적격성을 판정한다.
TBL_LOAN_APPLICATION.STATUS를 'APPROVED' 또는 'REJECTED'로 갱신하며,
SEQ_APPROVAL_HISTORY를 사용해 TBL_APPROVAL_HISTORY에 이력을 기록한다.
거절 사유는 LTV_EXCEEDED, CREDIT_LOW 등의 코드로 기록된다.
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
