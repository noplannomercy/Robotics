# Reverse-Doc Service — 설계 스펙

> **작성일**: 2026-04-27
> **범위**: Oracle 자산 역문서화 비동기 REST 마이크로서비스
> **프로젝트 위치**: `C:/workspace/reverse_doc_projece/`
> **Eng-review 완료**: 2026-04-27 (8개 이슈 반영)

---

## 1. 개요

Oracle 시스템 자산(PL/SQL 패키지, 데이터 딕셔너리, ERD, 업무 정책 문서)을 v2 표준 canonical 식별자 markdown으로 역문서화하는 비동기 REST 마이크로서비스.

**이 서비스가 하는 것:**
- Oracle 자산 파일 업로드 수신 (ingestion-router 경유)
- LightRAG에서 참조 컨텍스트 조회 (read-only, mix mode)
- LLM으로 v2 표준 역문서 생성 + 검증 (최대 3회 재시도)
- 완료 시 ingestion-router로 callback (markdown 결과 전달)
- 비동기 Job 상태 추적 (PostgreSQL)

**이 서비스가 하지 않는 것:**
- LightRAG insert (ingestion-router가 callback 수신 후 담당)
- Docling HybridChunker 청킹 (LightRAG insert와 함께 ingestion-router로 이동)
- AST / 결정론적 코드 분석 (LLM에 위임, hint 추출만 단순 정규식)
- 비정형 문서 변환 (Forge, port 8003 담당)

---

## 2. 스택

| 항목 | 선택 |
|------|------|
| 런타임 | Python 3.11+ |
| 프레임워크 | FastAPI + uvicorn |
| HTTP 클라이언트 | httpx (async) |
| DB 드라이버 | asyncpg |
| 설정 관리 | pydantic-settings |
| 포트 | 8004 |
| DB | PostgreSQL (Forge/ingestion-router와 동일 인스턴스, `rdoc_*` 테이블) |

---

## 3. 파일 구조

```
reverse_doc_projece/
├── config.py          — 환경변수 (pydantic-settings)
├── models.py          — Pydantic 모델 (Job, Request, Response)
├── job_store.py       — JobStore ABC + InMemoryJobStore + PostgresJobStore + PromptStore
├── schema.sql         — DDL (IF NOT EXISTS, idempotent)
├── auth.py            — verify_api_key() factory (미설정 시 비활성)
├── worker.py          — 비동기 워커 루프 + _safe_process 래퍼
├── app.py             — FastAPI 엔트리포인트 (5 엔드포인트)
├── admin.py           — 관리 API (2 엔드포인트, auth gated)
├── llm_client.py      — OpenAI-compatible 비동기 LLM 클라이언트
├── rag_client.py      — LightRAG REST API 쿼리 전용 클라이언트
├── validator.py       — 역문서 품질 검증 (check 1-4)
├── prompts.py         — PromptStore 초기 시드 콘텐츠 (asset_type별)
├── processor.py       — 역문서화 파이프라인 오케스트레이터
├── callback.py        — ingestion-router 콜백 전송 (3회 retry)
├── Dockerfile
├── .env.example
└── tests/
    ├── test_config.py
    ├── test_models.py
    ├── test_job_store.py
    ├── test_validator.py
    ├── test_llm_client.py
    ├── test_rag_client.py
    ├── test_processor.py
    ├── test_callback.py
    ├── test_app.py
    └── test_e2e.py    — Mock E2E (POST /jobs → worker → GET /jobs/{id}/result)
```

---

## 4. 환경변수

```env
# LLM (OpenAI-compatible — Bedrock, OpenRouter, Ollama 등)
LLM_URL=http://localhost:11434/v1/chat/completions
LLM_MODEL=qwen2.5:14b
LLM_API_KEY=
LLM_TIMEOUT=120
LLM_CONCURRENCY=3

# LightRAG (쿼리 전용)
LIGHTRAG_URL=http://lightrag:8080
LIGHTRAG_API_KEY=
RAG_TIMEOUT=60

# 서비스
DATABASE_URL=postgresql://user:pass@host:5432/dbname
ADMIN_API_KEY=                    # 미설정 시 admin 인증 비활성
MAX_FILE_SIZE_KB=200
PORT=8004
HOST=0.0.0.0
```

---

## 5. DB 스키마

```sql
CREATE TABLE IF NOT EXISTS rdoc_job (
    job_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_type   TEXT NOT NULL,          -- 'plsql' | 'dictionary' | 'erd' | 'policy'
    file_name    TEXT NOT NULL,
    source_hash  TEXT NOT NULL,          -- sha256(source_bytes + prompt_version)
    status       TEXT NOT NULL DEFAULT 'queued',
                                         -- queued | processing | completed | failed
    result       TEXT,                   -- 완료된 역문서 markdown
    error        TEXT,
    attempts     INT DEFAULT 0,          -- LLM 재시도 횟수
    callback_url TEXT,
    requested_by TEXT,
    created_at   TIMESTAMPTZ DEFAULT now(),
    started_at   TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_rdoc_job_source_hash ON rdoc_job(source_hash);

CREATE TABLE IF NOT EXISTS rdoc_prompt (
    id           SERIAL PRIMARY KEY,
    asset_type   TEXT NOT NULL,
    version      TEXT NOT NULL,
    text         TEXT NOT NULL,
    is_active    BOOLEAN DEFAULT true,
    created_at   TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_rdoc_prompt_active
    ON rdoc_prompt(asset_type) WHERE is_active = true;
```

**source_hash 멱등성 규칙:**
- `source_hash = sha256(source_bytes + prompt_version.encode())`
- POST /jobs 시 동일 hash 존재 → 기존 job_id 반환 (재처리 없음)
- 프롬프트 버전 변경 시 hash도 달라져 재처리 트리거

---

## 6. API 엔드포인트

### 비동기 Job

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/jobs` | 역문서화 job 생성 (multipart: file + asset_type + callback_url) |
| GET | `/jobs/{job_id}` | job 상태 조회 |
| GET | `/jobs/{job_id}/result` | 완료된 역문서 조회 (미완료 시 404) |
| DELETE | `/jobs/{job_id}` | job 취소/삭제 |
| GET | `/health` | 헬스체크 |

### 관리 (ADMIN_API_KEY 인증)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/admin/jobs` | job 목록 (status, asset_type 필터, page/size) |
| POST | `/admin/jobs/{job_id}/retry` | 실패 job 강제 재시도 |

### 요청/응답 예시

```
POST /jobs
Content-Type: multipart/form-data

file=<PKG_AUTO_LOAN_APPROVAL.sql>
asset_type=plsql
callback_url=http://ingestion-router:8001/callback/forge?file_id=xxx
requested_by=ingestion-router

→ 202 {"job_id": "...", "status": "queued"}
```

```
GET /jobs/{job_id}/result

→ 200 {"job_id": "...", "status": "completed", "result": "# PKG_AUTO_LOAN_APPROVAL 역문서\n..."}
→ 404 {"detail": "job not completed or not found"}
```

---

## 7. 역문서화 파이프라인

```
processor.py — to_reverse_doc()

1. extract_hint_keywords(source)
   - 정규식: r'\b(?:TBL|PROC|FUNC|PKG|SEQ|FK|PK)_[A-Z0-9_]+\b'
   - SQL 키워드(BEGIN, END, IF 등) 제외
   - 결과: "PKG_AUTO_LOAN_APPROVAL PROC_CREDIT_EVALUATION TBL_LOAN_APPLICATION ..."

2. rag_client.query(hint, mode="mix")
   - 실패 또는 빈 응답 → "" + WARN 로깅 (job 계속 진행)
   - RAG_TIMEOUT 초과 시 동일 처리

3. prompt_store.get_active(asset_type)
   - rdoc_prompt 테이블에서 is_active=true 레코드 조회
   - 버전 정보도 함께 반환 (source_hash 계산에 사용)

4. llm_client.generate(system=prompt, user=f"[원문]\n{source}\n\n[참조 컨텍스트]\n{context}")
   - asyncio.Semaphore(LLM_CONCURRENCY) 으로 동시 호출 제한
   - LLM_TIMEOUT 초과 시 → job FAILED

5. validator.validate(raw=source, reverse=result)
   - check 1: project 식별자 누락 없는지 (prefix 패턴 기준)
   - check 2: 식별자가 모두 대문자 underscore인지
   - check 3: enum 값이 모두 TBL.COL='val' 형태인지 (단독 'REJECTED' 금지)
   - check 4: 컬럼명 단독 등장 없는지 (항상 점 표기)
   - 실패 시 실패한 check 번호 + 구체적 항목을 feedback으로 반환

6. 검증 실패 시 재시도 (최대 3회)
   - 프롬프트에 ## 재시도 피드백\n{feedback} 섹션 append
   - 예: "check 1 실패: TBL_CUSTOMER_MASTER 누락. check 3 실패: 'APPROVED' 단독 등장"
   - 3회 모두 실패 → job FAILED (마지막 생성 결과 보존)

7. job_store.save_result(job_id, result)
   - status → completed

8. callback.send(callback_url, payload)
   - payload: {forge_job_id, content: markdown, forge_status, forge_error}
   - Forge worker.py와 동일 payload 구조 (ingestion-router 호환)
   - 3회 retry (1s, 2s, 4s 간격)
   - callback 실패 시 로그만 (job status에 영향 없음)
```

---

## 8. 핵심 모듈 설계

### `llm_client.py`

```python
class LLMClient:
    def __init__(self, config: Config):
        self.semaphore = asyncio.Semaphore(config.llm_concurrency)
        self._client = httpx.AsyncClient(timeout=config.llm_timeout)

    async def generate(self, system: str, user: str, model: str | None = None) -> str:
        async with self.semaphore:
            # POST {LLM_URL} with OpenAI chat format
            # 3회 retry on transient error (5xx, timeout)
            ...
```

### `rag_client.py`

```python
class RAGClient:
    async def query(self, query: str, mode: str = "mix") -> str:
        """LightRAG REST API 쿼리. 실패 시 "" 반환."""
        ...
```

### `validator.py`

```python
PROJECT_ID_PATTERN = re.compile(r'\b(?:TBL|PROC|FUNC|PKG|SEQ|FK|PK)_[A-Z0-9_]+\b')
STANDALONE_QUOTED_ENUM = re.compile(r"(?<!\w\.')'[A-Z][A-Z0-9_]+'")
STANDALONE_COLUMN = re.compile(r'(?<!\w\.)\b[A-Z][A-Z0-9_]+\b(?!\s*=)')

@dataclass
class ValidationResult:
    passed: bool
    feedback: str | None  # 실패 시 재시도 프롬프트에 append할 한국어 메시지

def validate(raw: str, reverse: str) -> ValidationResult:
    ...
```

### `processor.py`

```python
async def to_reverse_doc(
    raw: bytes,
    asset_type: str,
    job_id: str,
    callback_url: str | None,
    store: JobStore,
    llm: LLMClient,
    rag: RAGClient,
    prompt_store: PromptStore,
) -> None:
    ...
```

---

## 9. 테스트 전략

| 파일 | 범위 |
|------|------|
| `test_validator.py` | check 1-4 pass/fail, SQL 키워드 제외, 재시도 feedback 메시지 |
| `test_processor.py` | 성공 경로, 재시도 1-2회 후 성공, 3회 실패, RAG 실패 fallback |
| `test_llm_client.py` | 정상 응답, 타임아웃, 5xx, Semaphore 동시 제한 |
| `test_rag_client.py` | 정상 응답, 연결 실패, 빈 응답 |
| `test_job_store.py` | create/get/update_status/save_result, source_hash 중복 |
| `test_app.py` | 각 엔드포인트 happy path + 에러 케이스 |
| `test_callback.py` | 성공, URL 없음 skip, 3회 실패 후 로그 |
| `test_e2e.py` | POST /jobs → worker 실행 → GET /jobs/{id}/result 전체 흐름 (Mock LLM/RAG) |

**Mock 전략:**
- LLM/LightRAG: `httpx.MockTransport` 또는 `unittest.mock.AsyncMock`
- DB: `InMemoryJobStore` (PostgreSQL 불필요)
- E2E: `httpx.AsyncClient(app=app)` + 위 두 가지 결합

---

## 10. 통합 컨텍스트

```
Bitbucket PR merge
  ↓
hcs-ingestion-router (port 8001)
  ├── .sql/.pkb → POST /jobs (this service, port 8004)
  └── .pdf/.docx → POST /convert (Forge, port 8003)

this service
  ├── LightRAG query (read-only, context 조회)
  ├── LLM generate + validate
  └── callback → POST /callback/forge (ingestion-router)

ingestion-router (callback 수신)
  ├── forge_status 업데이트
  └── POST /documents/text (LightRAG insert)
```

**ingestion-router 업데이트 필요 (별도 세션):**
- `REVERSE_DOC_URL=http://reverse-doc:8004` 환경변수 추가
- `.sql/.pkb` 라우팅을 `REVERSE_DOC_URL/jobs`로 변경
- 현재 스펙은 `FORGE_URL/reverse-doc`으로 잘못 기록됨

---

## 11. 제약 사항

| # | 규칙 | 이유 |
|---|------|------|
| C1 | AST/식별자 스캐너/딕셔너리 lookup 금지 | RAG+LLM 컨셉 훼손 방지 |
| C2 | `asyncio.create_task` 시 반드시 `_safe_process` 래퍼 | fire-and-forget 예외 삼킴 방지 |
| C3 | LightRAG insert 금지 (query only) | ingestion-router가 소유 |
| C4 | chunk/Docling 의존성 추가 금지 | ingestion-router 영역 |
| C5 | `source_hash` 없는 job 생성 금지 | 멱등성 보장 |

---

## 12. 미확정 사항

| 항목 | 상태 |
|------|------|
| LightRAG REST API 경로/포트 | 실제 구동 버전 확인 필요 |
| ingestion-router 라우팅 업데이트 | 별도 세션 |
| 동시 job 순서 보장 (RAG context) | PoC에서 허용, WARN 로깅 |

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 1 | issues_found | 5 findings (4 반영, 1 TODO) |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR | 8 issues, 0 critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

**VERDICT: ENG CLEARED — 구현 시작 가능**
