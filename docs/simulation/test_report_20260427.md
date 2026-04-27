# 역문서화 파이프라인 검증 리포트

> 일자: 2026-04-27  
> 대상: PKG_AUTO_LOAN_APPROVAL.sql  
> 환경: LightRAG (193.168.195.222:9621) + OpenRouter deepseek-chat

---

## 테스트 시나리오

### Phase 1 — LightRAG 컨텍스트 주입 (선행)

| 순서 | 파일 | 설명 |
|------|------|------|
| 1 | `dictionary/schema.md` | 테이블/컬럼 정의 (TBL_LOAN_APPLICATION 등) |
| 2 | `refs/01_credit_evaluation_policy.md` | 신용평가 정책 (600점 기준 등) |
| 3 | `refs/02_loan_limit_policy.md` | 대출한도 정책 (연소득×5, 가중치) |
| 4 | `refs/03_notification_policy.md` | 알림 정책 (SMS 메시지 등) |

### Phase 2 — 역문서화

| 항목 | 값 |
|------|-----|
| 입력 파일 | `source/PKG_AUTO_LOAN_APPROVAL.sql` (260줄) |
| asset_type | plsql |
| callback_url | http://193.168.195.222:9621/documents/text |
| 소요 시간 | 약 10분 |
| 시도 횟수 | 1회 (재시도 없이 통과) |
| validator | check 1 (식별자 누락), check 2 (대소문자) |

---

## 그래프 쿼리 검증 결과

### Q1. TBL_APPROVAL_HISTORY에 데이터를 기록하는 프로시저는?

**References**: `PKG_AUTO_LOAN_APPROVAL.sql`

**결과**: PROC_FINAL_APPROVAL, 컬럼(APPLICATION_ID, EVAL_TYPE, RESULT, EVAL_DATE) 식별  
**판정**: ✅ 역문서 단독 답변

---

### Q2. PROC_CREDIT_EVALUATION 신용점수 통과 기준은?

**References**: `01_credit_evaluation_policy.md`, `07_신용점수관리.md`

**결과**: 600점 이상 통과, KCB/NICE 외부 기관, 연체 3건 조건  
**판정**: ✅ **역문서 ↔ 정책 크로스 참조 성공** (소스에 없는 숫자 정보 추출)

---

### Q3. 신용평가 거절 시 고객 알림 흐름은?

**References**: `01_credit_evaluation_policy.md`, `03_notification_policy.md`

**결과**: PROC_NOTIFY_APPLICANT, SMS "신용평가 결과 승인이 어렵습니다.", TBL_NOTIFICATION_LOG  
**판정**: ✅ **정책 2개 멀티홉 성공**

---

### Q4. FUNC_LIMIT_CALCULATION 대출 한도 공식은?

**References**: `02_loan_limit_policy.md`

**결과**: 기본한도=연소득×5, 신용점수 구간별 가중치(1.5/1.2/1.0/0.7)  
**판정**: ✅ **역문서 ↔ 정책 크로스 참조 성공**

---

### Q5. 대출 신청 최종 승인까지 전체 처리 흐름은?

**References**: `PKG_AUTO_LOAN_APPROVAL.sql`, `01_credit_evaluation_policy.md`, `02_loan_limit_policy.md`, `03_notification_policy.md`, `02_심사정책.md`

**결과**: 5단계 흐름 (접수→신용평가→한도산정→최종승인→알림) + 거절 조건 포함  
**판정**: ✅ **역문서 + 딕셔너리 + 정책 3종 종합 멀티홉 성공**

---

## 핵심 발견

### 1. 순서 투자 효과 실증

딕셔너리/정책을 먼저 주입한 상태에서 역문서화하면 **소스 코드에 없는 비즈니스 정보**(600점, 연소득×5, SMS 메시지 등)가 그래프 연결을 통해 답변에 포함됨.

### 2. validator check 3/4 제거 결정

regex 기반 enum/컬럼 표기 검증은 Oracle 예외명, OUT 파라미터 대입값 등 false positive 누적이 불가피함. check 1+2만 유지하고 표기 규칙은 프롬프트로 유도하는 방식으로 전환.

### 3. 처리 시간

deepseek-chat + 260줄 소스 + RAG 컨텍스트 기준 약 10분. 속도 개선 필요 시 모델 교체 검토.

### 4. 캐시 주의사항

동일 소스+프롬프트 버전 조합은 source_hash로 캐시됨. 재처리 필요 시 반드시 `DELETE /jobs/{id}` 먼저 실행.
