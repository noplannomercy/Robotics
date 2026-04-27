# 시뮬레이션 결과 (현대캐피털 오토론 도메인)

## 시뮬 자산

```
docs/simulation/
├── source/
│   └── PKG_AUTO_LOAN_APPROVAL.sql      # 5 PROC/FUNC
├── dictionary/
│   └── schema.md                        # TBL 6개 + PK/FK/SEQ
├── refs/
│   ├── 01_credit_evaluation_policy.md
│   ├── 02_loan_limit_policy.md
│   └── 03_notification_policy.md
└── reverse_doc/
    └── PKG_AUTO_LOAN_APPROVAL.md       # v2 표준 적용
```

도메인: 자동차 할부 승인 (신청 접수 → 신용평가 → 한도 산정 → 최종 승인 → 알림).

## v1 → v2 표준 개선 (4가지 borderline 해소)

시뮬 1차 (v1)에서 발견된 분열/노이즈 위험:

| 위반 | v1 | v2 (확정) |
|---|---|---|
| (가) 코드값 enum 충돌 | `'REJECTED'` 단독 → STATUS와 RESULT 두 컬럼 값에서 충돌, 같은 노드로 자동 merge되어 의미 섞임 | `TBL.컬럼 = '값'` 형태 강제 |
| (나) 컬럼명 단독 | `EVAL_TYPE`, `RESULT`, `NOTIFY_TYPE` 단독 등장 | 모두 점 표기 (`TBL_APPROVAL_HISTORY.EVAL_TYPE`) |
| (다) 자연어 동의어 분열 | "연소득" 단독 → `TBL_CUSTOMER_MASTER.ANNUAL_INCOME`과 별개 노드로 분열 위험 | 같은 문장에 점 표기 동반 ("이 연소득") |
| (라) 정책 위계 모호 | "LTV 제한" 단독 → 어느 정책 소속인지 모호 | "대출 한도 산정 정책의 LTV 제한" 동반 |

**Entity 변화**:
- 사라진 노이즈 노드: `'APPROVED'`, `'REJECTED'`, `'RECEIVED'`, `'ACTIVE'`, `EVAL_TYPE`, `RESULT`, `NOTIFY_TYPE` (7개)
- 강화된 컬럼 단위 노드: `TBL_LOAN_APPLICATION.STATUS`, `TBL_APPROVAL_HISTORY.EVAL_TYPE` 등 — description에 enum 값 누적

## Q&A 시뮬 (mix mode 11개 쿼리)

기준 패턴: 정책 위계 entity → 코드 → 데이터 → 거절코드 → 알림까지 4-way traverse.

### 비즈니스/코드 횡단

| Q | 결과 |
|---|---|
| Q1. 오토론 신청부터 승인까지 전체 흐름은? | 5 PROC 체인 + 거절 분기 + 정책 적용 풍부 ✓ |
| Q2. PROC_CREDIT_EVALUATION이 어떤 기준으로 거절해? | CREDIT_LOW / LIMIT_EXCEEDED 두 거절 + 후속 처리 정확 ✓ |

### 컬럼 단위 추적 (v2 효과 핵심)

| Q | 결과 |
|---|---|
| Q3. TBL_LOAN_APPLICATION.STATUS는 어떻게 변해? | 'RECEIVED' / 'REJECTED' / 'APPROVED' 변경 PROC 명확 ✓ |
| Q6. TBL_APPROVAL_HISTORY.EVAL_TYPE = 'CREDIT'은 뭐야? | 컬럼 description에 'CREDIT'/'LIMIT'/'FINAL' 통합 답변 ✓ |

v1이었으면 'REJECTED' 노드가 두 컬럼 값에 동시 묶여 답변 흐려졌을 것. v2에선 컬럼 단위로 깔끔.

### 정책/코드 매핑

| Q | 결과 |
|---|---|
| Q4. 신청자 알림은 어떤 경우에 발송돼? | 3 케이스 + 사전 반려 미발송 정책까지 자동 따라옴 ✓ |
| Q5. 신용점수 가중치는 어떻게 적용돼? | 대출 한도 산정 정책 + 신용평가 정책 위계 명확 ✓ |

### 정책 위계 패턴 5종 (Q5 기준)

| Q | 결과 |
|---|---|
| Q7. LTV 제한은 어떻게 적용돼? | 대출 한도 산정 정책 → PROC_LOAN_APPLICATION_RECEIVE → LTV_EXCEEDED → 사전 반려 미발송 ✓ |
| Q8. 연체 이력 기준은 뭐야? | 신용평가 정책 → PROC_CREDIT_EVALUATION → TBL_OVERDUE_HISTORY → CREDIT_LOW (통합 코드 미묘 정책 보존) ✓ |
| Q9. 기본 한도는 어떻게 산출돼? | 대출 한도 산정 정책 → FUNC_LIMIT_CALCULATION → ANNUAL_INCOME × 5 → ANNUAL_INCOME 누락 시 별도 검토 정책까지 ✓ |
| Q10. 발송 채널은 뭐야? | 신청자 알림 발송 정책 → PROC_NOTIFY_APPLICANT → SMS / TBL_CUSTOMER_MASTER.PHONE / 비동기 처리 ✓ |
| Q11. 대출 기간 제한은 어떻게 적용돼? | 대출 한도 산정 정책 → 60개월 → PROC_LOAN_APPLICATION_RECEIVE → PERIOD_EXCEEDED → 미발송 ✓ |

## 핵심 발견

**잘 되는 것**:
- 코드/데이터/업무 entity 3-way가 답변 한 단락에 자연 공존
- refs(정책 문서)와 역문서가 한 그래프에서 자동 결합 → 정책 질문 시 양쪽 청크 모두 retrieve
- 컬럼 단위 노드가 description에 enum 값을 누적 → 컬럼값 질문에 강함
- 양방향 traverse (컬럼 → PROC들, 정책 → 코드, 거절 코드 → 발생 케이스)
- refs에만 있는 미묘한 조항(CREDIT_LOW 통합, ANNUAL_INCOME 누락 별도 검토, 비동기 처리)이 답변에 정확 반영

**v2 표준의 효과**:
- 컬럼 추적 / 정책 위계 / 컬럼값 의미 질문에서 v1 대비 명백 개선
- "대출 한도 산정 정책의 LTV 제한" 동반 표기가 정책 위계 traverse 보장

**남은 한계**:
- 답변 본문에 식별자 빽빽 → 사람이 읽기엔 코드스러움. 다만 그래프 KB는 사람 읽기용 문서가 아니므로 OK
- 답변 LLM의 식별자 보존 vs 자연어화는 답변 LLM 프롬프트로 조정 가능 영역

## 결론

v2 표준 + Docling 헤더 청킹 + LightRAG mix mode 조합으로 **온보딩/분석/설계/소스 본질 파악** 요건 충족. AST 미사용. 의미 그래프가 요건에 더 적합한 답.

다음 단계: 파이프라인 구현 (`docs/pipeline.md` 참조).
