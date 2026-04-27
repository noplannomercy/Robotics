# 역문서 생성 규칙 (표준)

## 핵심 원칙

1. **식별자를 문법적 주체/객체 자리에 박는다** — 한국어 조사(는/가/를/에서/에)가 식별자 뒤에 자연스럽게 붙음. 부연/괄호가 아닌 anchor 위치.
2. **업무 entity와 코드 entity를 같은 문장(또는 인접 문장)에 공존시킨다** — 한 문장 내 공존이 그래프 엣지를 만든다.
3. **한 단락 = 한 단위 (PROC/FUNC, TBL, 정책, ...)** — 단락 첫 문장에 식별자가 주어로. 단락 응집도 = 청크 응집도.

## 표기 규칙

| 종류 | 표기 | 예시 |
|---|---|---|
| 패키지 | `PKG_*` 그대로 | `PKG_AUTO_LOAN_APPROVAL` |
| 프로시저/함수 | `PROC_*` / `FUNC_*` 그대로 | `PROC_CREDIT_EVALUATION` |
| 테이블 | `TBL_*` 그대로 | `TBL_LOAN_APPLICATION` |
| 컬럼 | `테이블.컬럼` 점 표기 | `TBL_LOAN_APPLICATION.STATUS` |
| 시퀀스 | `SEQ_*` 그대로 | `SEQ_LOAN_APPLICATION` |
| FK/PK | `FK_*` / `PK_*` 그대로 | `FK_LOAN_APP_CUSTOMER` |
| 코드값 enum | `TBL.컬럼 = '값'` 형태 강제 | `TBL_LOAN_APPLICATION.STATUS = 'APPROVED'` |
| 거절 사유 코드 | unquoted upper underscore 단독 허용 | `CREDIT_LOW`, `LTV_EXCEEDED` |
| 업무 entity | refs(업무 KB)의 canonical 표기와 정확히 일치 | `신용평가 정책`, `대출 한도 산정 정책` |

## 금지 패턴

- **번역/풀어쓰기 금지**: "신용평가 프로시저" ✗ → `PROC_CREDIT_EVALUATION` ✓
- **대소문자 변형 금지**: `proc_credit_evaluation` ✗
- **식별자를 괄호 부연으로 빼기 회피**: "신용을 평가하는 프로시저(PROC_CREDIT_EVALUATION)" ✗ → 식별자를 주어로
- **업무 entity 동의어 사용 금지**: "신용평가 기준" / "신용 정책" 혼용 ✗ → canonical 표기 하나만
- **코드값 enum 단독 등장 금지**: `'REJECTED'` ✗ (STATUS와 RESULT 두 컬럼 값에서 충돌) → `TBL.컬럼 = '값'` 형태로
- **컬럼명 단독 등장 금지**: `EVAL_TYPE`, `RESULT`, `NOTIFY_TYPE` ✗ → 항상 점 표기로
- **자연어 컬럼 동의어 단독 사용 금지**: "연소득" ✗ → 같은 문장에 점 표기 동반 ("TBL_CUSTOMER_MASTER.ANNUAL_INCOME을 조회하여 이 연소득의 5배")
- **세부 정책 단독 등장 금지**: "LTV 제한" 단독 ✗ → "대출 한도 산정 정책의 LTV 제한"

## 권장 단락 (예시)

```
PROC_CREDIT_EVALUATION은 신용평가 정책에 따라 신청 건의 신용 적격성을
판정한다. 신용평가 정책의 신용점수 기준에 따라 TBL_CREDIT_SCORE.CREDIT_SCORE가
600점 미만이거나 연체 이력이 3건 이상인 경우 PROC_CREDIT_EVALUATION은
TBL_LOAN_APPLICATION.STATUS = 'REJECTED'로 변경하고 TBL_LOAN_APPLICATION.REJECT_REASON에
CREDIT_LOW를 기록한다. 동시에 PROC_CREDIT_EVALUATION은 TBL_APPROVAL_HISTORY.EVAL_TYPE
= 'CREDIT'과 TBL_APPROVAL_HISTORY.RESULT = 'REJECTED'로 평가 이력을 적재하고,
TBL_NOTIFICATION_LOG.NOTIFY_TYPE = 'REJECT_CREDIT'으로 PROC_NOTIFY_APPLICANT를
호출하여 신용평가 거절 알림을 발송한다.
```

## 검증 항목 (insert 전 자동)

1. 입력 원문의 모든 식별자가 역문서에 등장하는가 (정규식 ∩ 비교 — 누락 없음)
2. 식별자 표기가 100% canonical인가 (정규식 매칭)
3. 업무 KB의 정책 entity가 역문서에 표기 일치로 등장하는가
4. 코드값 enum이 모두 `TBL.컬럼 = '값'` 형태인가 (단독 따옴표 enum 금지)
5. 컬럼명이 모두 점 표기인가 (단독 컬럼명 금지)

3회 재생성 실패 시 사람 검토 큐로.

## 자산 유형별 단위

| 자산 | 단락 단위 | 핵심 entity 패턴 |
|---|---|---|
| 딕셔너리 | TBL 단위 | `TBL_*`, 점 표기 컬럼, `FK_*`, `PK_*` |
| ERD | TBL 간 관계 단위 | `TBL_X.컬럼 → TBL_Y.컬럼 (1:N)` 자연어 |
| 업무 정책 | 정책 단위 | 정책 canonical 명 |
| API 명세 | 엔드포인트 단위 | `API_*`, `DTO_*` |
| PL/SQL 패키지 | PROC/FUNC 단위 | `PKG_*`, `PROC_*`, `FUNC_*` |

표기 규칙은 모든 자산 공통.
