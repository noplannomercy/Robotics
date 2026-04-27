## 오라클 PL/SQL 역문서화 파이프라인 개념증명 (PoC)

### 배경 및 목표

오라클 PL/SQL 패키지 소스코드에서 비즈니스 로직을 추출해 LightRAG(RAG+Graph) 기반 지식 시스템으로 구축하는 파이프라인을 테스트한다. 핵심 목표는 두 가지다.

1. **온보딩 용도** (현재 잘 되는 것): 비즈니스 로직 분석/설계/이해
2. **코드 생성 용도** (보완 필요): 소스 패턴/템플릿 추출 → 실제 코드 작성에 활용, 소스 추적성 및 종속성 확보

---

### 핵심 아이디어: 비즈니스 설명 내 식별자 자연 노출

역문서화의 기본 방향은 **비즈니스 도메인 관점의 자연어 서술**을 유지한다. 여기에 별도 태그나 구조를 추가하는 것이 아니라, 자연어 설명 자체 안에 소스코드의 실제 식별자(패키지명, 프로시저명, 함수명, 테이블명 등)를 자연스럽게 노출시킨다.

이렇게 하면 세 가지 효과가 동시에 달성된다.

**첫째, 청킹 논리 경계 확보**: 소스의 PROCEDURE/FUNCTION 경계가 비즈니스 로직의 논리 경계와 일치한다. 역문서에서 프로시저 이름이 명시적으로 등장하면 Docling Hybrid Chunking이 그 경계를 논리 단위로 인식해 의미있게 분리한다.

**둘째, 소스 추적성 확보**: 역문서의 어느 청크가 소스의 어느 프로시저/함수에서 왔는지를 식별자를 통해 역추적할 수 있다.

**셋째, 그래프 관계 자동 생성**: LightRAG가 청크를 처리할 때 본문에 등장하는 식별자들(PKG_APPROVAL, PROC_APPROVAL_CHECK, TBL_APPROVAL_MASTER 등)을 엔티티 노드로 인식하고, 설명 문맥에서 이들 간의 관계를 엣지로 자동 추출한다. 별도의 그래프 구축 작업 없이 자연어 설명 자체가 그래프의 노드와 엣지를 내포하게 된다.

**역문서 작성 예시:**

```
PKG_APPROVAL의 승인 검증 프로세스는 결재 요청이 접수되면
PROC_APPROVAL_CHECK를 통해 결재자의 권한 레벨과 위임 여부를
확인한다. 권한 레벨이 3 미만이거나 위임 상태인 경우 승인이
거부되며, PROC_NOTIFY_APPROVER를 호출하여 결재자에게 알림을
발송한다. 이 과정에서 TBL_APPROVAL_MASTER에 승인 이력이 기록된다.
```

---

### 현재 파이프라인 구조

```
오라클 패키지 소스 (PL/SQL)
        ↓
  [전처리: PACKAGE/PROCEDURE/FUNCTION 단위 분리]
        ↓
  [역문서화 LLM]  ← 기존 LightRAG의 업무도메인 KB 참조
        ↓
  비즈니스 자연어 역문서 (식별자 포함)
        ↓
  [Docling Hybrid Chunking] ← 식별자 기준 논리 경계로 분리
        ↓
  LightRAG (RAG + Graph) ← 식별자가 노드/엣지로 자동 생성
```

---

### PoC 테스트 항목

#### 1단계: PL/SQL 전처리기 구현

오라클 패키지 소스를 PACKAGE/PROCEDURE/FUNCTION 단위로 분리하는 전처리기를 구현한다. ANTLR 같은 무거운 파서 없이 PL/SQL의 규칙적인 구조 패턴(CREATE OR REPLACE PROCEDURE/FUNCTION, BEGIN/END 블록 경계)을 활용한 간단한 파싱으로 구현한다.

참고 가능한 오픈소스:
- `codeLong1024/plsql-parser` — ANTLR4 기반 Go 파서, Oracle EBS 특화. PACKAGE/PROCEDURE/FUNCTION/SQL_STATEMENT 노드 추출 및 L2 최적화(토큰 30~50% 절감) 지원. 신생 레포(star 0)이므로 구조 참고용으로 활용.
- `antlr/grammars-v4/sql/plsql` — ANTLR 공식 PL/SQL 문법. `antlr4-python3-runtime`으로 Python 바인딩 사용 가능. 검증된 문법이나 직접 파서 구현 필요.

**검증 목표**: 샘플 PL/SQL 패키지를 입력했을 때 PACKAGE/PROCEDURE/FUNCTION 단위로 올바르게 분리되는지 확인.

#### 2단계: 역문서 생성 프롬프트 설계

분리된 각 단위(PROCEDURE, FUNCTION)를 LLM에 입력해 역문서를 생성한다. 프롬프트의 핵심 지시사항은 다음과 같다.

- 서술 관점은 반드시 **업무/비즈니스 도메인**을 기준으로 한다
- 소스의 실제 식별자(패키지명, 프로시저명, 테이블명, 호출 대상 등)를 자연어 문장 안에 자연스럽게 포함시킨다
- 별도 태그, 메타데이터 섹션, 구조 분리 없이 순수 자연어 서술로 작성한다
- 비즈니스 규칙(조건, 예외, 흐름)이 명확하게 드러나야 한다

**검증 목표**: 생성된 역문서가 비즈니스 관점을 유지하면서 식별자가 본문 안에 자연스럽게 포함되는지 확인. 동일 소스에 대해 반복 실행 시 식별자 포함이 일관되게 유지되는지 확인.

#### 3단계: Docling Hybrid Chunking 검증

생성된 역문서를 Docling으로 청킹했을 때 프로시저/함수 논리 단위로 의미있게 분리되는지 확인한다.

**검증 목표**: 각 청크가 하나의 PROCEDURE/FUNCTION에 대한 완전한 비즈니스 설명을 담고 있는지, 식별자(PROC_APPROVAL_CHECK 등)가 청크 내에 온전히 포함되는지, 청크 경계에서 의미가 끊기지 않는지 확인.

#### 4단계: LightRAG 그래프 노드/엣지 생성 검증

청킹된 결과를 LightRAG에 태웠을 때 소스 식별자들이 그래프 노드로 인식되고, 비즈니스 설명 문맥에서 식별자 간 관계가 엣지로 자동 생성되는지 확인한다.

**검증 목표**: `PROC_APPROVAL_CHECK → PROC_NOTIFY_APPROVER`, `PROC_APPROVAL_CHECK → TBL_APPROVAL_MASTER` 같은 관계가 그래프에 올바르게 나타나는지, 쿼리 시 비즈니스 설명과 소스 추적이 동시에 가능한지 확인.

---

### 향후 확장 방향

- 현재: 오라클 PL/SQL 패키지 중심
- 추후: 백엔드(Java/Python 등), 프론트엔드(JS/TS 등)는 **Graphify** (`safishamsi/graphify`, star 34k)로 AST 처리 후 LightRAG `merge-graphs`로 통합. Graphify는 동일한 식별자 기반 노드 매핑을 사용하므로 역문서의 식별자 앵커와 자연스럽게 연결된다. 현재 PL/SQL PROCEDURE/FUNCTION 파싱은 미지원 (SQL DDL extractor PR #458 진행 중).
