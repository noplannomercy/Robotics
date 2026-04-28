# Reverse-Doc Service — Feature Enhancements Design

> 작성일: 2026-04-29  
> 작성자: noplannomercy  
> 상태: 승인됨

## 개요

기존 Reverse-Doc Service(port 8004)에 4개의 독립적인 기능 그룹을 추가한다. 각 그룹은 별도 feature 브랜치로 구현되며 서로 의존성 없이 독립적으로 출하 가능하다.

---

## Group A — 프롬프트 관리 강화

### 목표
현재 `PUT /admin/prompts/{asset_type}`으로 새 버전 등록만 가능하다. 조회/히스토리/롤백이 없어 운영 중 현재 어떤 프롬프트가 활성화되어 있는지 확인할 수 없다.

### 추가 엔드포인트 (모두 `ADMIN_API_KEY` 인증 필요)

| 메서드 | 경로 | 기능 |
|--------|------|------|
| `GET` | `/admin/prompts/{asset_type}` | 현재 활성 프롬프트 조회 (text + version + created_at) |
| `GET` | `/admin/prompts/{asset_type}/history` | 전체 버전 목록 (버전번호, 활성여부, created_at — text 미포함) |
| `GET` | `/admin/prompts/{asset_type}/history/{version}` | 특정 버전 전체 조회 (text 포함) |
| `POST` | `/admin/prompts/{asset_type}/rollback/{version}` | 특정 버전 text를 새 버전으로 복사 + 활성화 |

### 롤백 방식
기존 버전을 직접 활성화하지 않고, 해당 버전의 `text`를 복사해서 새 버전으로 INSERT + 활성화. 버전 번호가 단조증가하여 히스토리가 꼬이지 않는다.

### 스키마 변경
없음. 기존 `rdoc_prompt` 테이블로 충분.

### 구현 파일
- `admin.py` — 4개 엔드포인트 추가
- `job_store.py` — `InMemoryPromptStore`와 `PromptStore`에 `list_versions()`, `get_version()` 메서드 추가

### 테스트
- `tests/test_admin.py` — 4개 엔드포인트 단위 테스트 (InMemory 기반)
- 롤백 후 새 버전 번호 = 이전 최대 버전 + 1 검증
- 존재하지 않는 asset_type/version 404 처리 검증

---

## Group B — Job 관리 강화

### 목표
1. 원본 소스를 DB에 저장하여 retry 시 재업로드 불필요하게 개선
2. 운영 통계 API 추가

### 스키마 변경

```sql
ALTER TABLE rdoc_job ADD COLUMN IF NOT EXISTS source_bytes BYTEA;
ALTER TABLE rdoc_job ADD COLUMN IF NOT EXISTS rag_mode TEXT DEFAULT 'mix';
```

> `rag_mode` 컬럼은 Group D와 공유. 두 그룹 중 먼저 배포하는 쪽이 마이그레이션 실행.

### retry 개선

`POST /admin/jobs/{id}/retry`:
- `source_bytes`가 있으면 원본으로 즉시 재처리 (새 job 생성)
- `source_bytes`가 없는 기존 레코드는 현재처럼 안내 메시지 반환 (하위 호환)

### 통계 API

`GET /admin/stats` (auth 필요):

```json
{
  "total": 142,
  "by_status": {
    "queued": 3,
    "processing": 1,
    "completed": 120,
    "failed": 18
  },
  "by_asset_type": {
    "plsql": 80,
    "dictionary": 40,
    "erd": 12,
    "policy": 10
  },
  "success_rate": 87.0,
  "avg_processing_sec": 12.4,
  "retry_rate": 8.5,
  "recent_failures": [
    {
      "job_id": "...",
      "file_name": "...",
      "error": "검증 실패 (3회): check 1 실패: TBL_LOAN_APPLICATION 누락",
      "failed_at": "2026-04-29T10:23:00Z"
    }
  ]
}
```

**지표 계산:**
- `success_rate` = `completed / total * 100` (total = 0이면 0.0)
- `avg_processing_sec` = `AVG(completed_at - started_at)` — **completed 상태이고 started_at, completed_at 모두 not None인 job만** 대상. PostgreSQL은 NULL 자동 제외, InMemoryJobStore는 명시적 필터 필수 (None 연산 시 TypeError)
- `retry_rate` = `attempts > 1인 job 수 / total * 100` (total = 0이면 0.0)
- `recent_failures` = 최근 5건 (failed, `completed_at DESC`)

### 구현 파일
- `schema.sql` — 컬럼 추가 (IF NOT EXISTS)
- `job_store.py` — `source_bytes` 저장/조회, `get_stats()` 메서드 추가 (`InMemoryJobStore` + `PostgresJobStore`)
- `app.py` — `POST /jobs`에서 `source_bytes=raw` 저장
- `admin.py` — retry 로직 개선, `GET /admin/stats` 추가

### 테스트
- `tests/test_job_store.py` — `source_bytes` 저장/조회 검증
- `tests/test_admin.py` — stats 응답 구조 검증, retry 자동화 검증
- stats: InMemory에 더미 job 삽입 후 집계값 검증

---

## Group C — 운영/모니터링

### 목표
`/health`가 `{"status":"ok"}` 고정이어서 DB 연결 실패 시에도 200을 반환한다. 큐 현황도 확인할 수 없다.

### 범위
**이 서비스의 자기 의존성만** 확인한다. LightRAG 등 연계 서비스 상태 집계는 ingestion-router 담당.

### 변경

`GET /health`:

- DB 연결 정상: `200 {"status": "ok", "queue": {"queued": N, "processing": N}}`
- DB 연결 실패: `503 {"status": "unavailable", "reason": "db"}`
- `DATABASE_URL` 미설정 (InMemory 모드): `200 {"status": "ok", "queue": {...}}`

> `queue` 카운트는 `list_jobs()` 대신 **경량 `count_by_status()` 메서드** 사용. `list_jobs()`는 페이지네이션 포함 무거운 메서드로 health endpoint에 부적합. `count_by_status()`는 `SELECT status, COUNT(*) FROM rdoc_job WHERE status IN ('queued','processing') GROUP BY status` 단일 쿼리.

### 구현 파일
- `job_store.py` — `JobStore` ABC + `InMemoryJobStore` + `PostgresJobStore`에 `count_by_status()` 추가
- `app.py` — `/health` 핸들러 강화

### 테스트
- `tests/test_app.py` — DB 없는 상태(InMemory)에서 200 + queue 포함 검증
- `tests/test_app.py` — DB 연결 실패 시 503: `pool.acquire()`를 AsyncMock으로 교체 후 `PostgresConnectionError` 발생 → 503 검증

---

## Group D — LightRAG 연계 강화

### 목표
RAG query mode가 `"mix"` 고정이어서 asset_type별 최적 mode 선택 불가.

### 변경

`POST /jobs`에 파라미터 추가:

```python
rag_mode: str = Form("mix")
```

**유효값:** `local`, `global`, `hybrid`, `mix`, `naive`  
**그 외:** `400 {"detail": "Invalid rag_mode: <value>. Must be one of: local, global, hybrid, mix, naive"}`

`rag_mode`는 `rdoc_job`에 저장 (추적 가능). `processor.py`의 `rag.query(hint, mode=rag_mode)` 전달.

> `source_bytes` 컬럼과 동일하게 `schema.sql`에 `ALTER TABLE rdoc_job ADD COLUMN IF NOT EXISTS rag_mode TEXT DEFAULT 'mix'` 추가. Group B와 먼저 배포하는 쪽이 마이그레이션 실행.

### 구현 파일
- `schema.sql` — `rag_mode` 컬럼 추가 (Group B와 동일 마이그레이션)
- `app.py` — `rag_mode` Form 파라미터, 유효성 검사
- `job_store.py` — `create()` + `_row_to_job()`에 `rag_mode` 반영
- `processor.py` — `to_reverse_doc()` 시그니처에 `rag_mode` 추가
- `worker.py` — `_safe_process()`에서 `rag_mode` 전달

### 테스트
- `tests/test_app.py` — 유효한 mode 값 전달 시 202, 유효하지 않은 값 400 검증
- `tests/test_processor.py` — `rag.query()` 호출 시 mode 파라미터 전달 검증

---

## 구현 순서 및 Merge 전략

4개 그룹은 완전히 독립적이다. 단 `job_store.py`, `admin.py`를 Group A/B/D가 모두 수정하므로 **반드시 순차 merge**해야 한다.

**필수 규칙: 각 그룹 feature 브랜치를 master에 merge 완료한 뒤, 다음 그룹 브랜치를 master에서 새로 생성한다.**

권장 순서: **A → C → D → B**
1. `feature/group-a` → master merge
2. `feature/group-c` (master에서 신규 생성) → master merge
3. `feature/group-d` (master에서 신규 생성) → master merge
4. `feature/group-b` (master에서 신규 생성) → master merge

**스키마 마이그레이션 (Group B + D 공유):**
- 먼저 배포하는 그룹(D)이 `source_bytes`와 `rag_mode` 컬럼 모두 추가 (`IF NOT EXISTS`)
- 나중에 배포하는 그룹(B)의 `ALTER TABLE`은 이미 컬럼이 있어도 에러 없이 통과

---

## 완료 조건

```bash
pytest tests/ -v        # 전체 테스트 통과
python main.py          # port 8004 기동
curl http://localhost:8004/health  # queue 포함 응답
```
