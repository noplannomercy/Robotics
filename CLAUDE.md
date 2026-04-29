# Robotics

## 작업 시작 전

**추가 피쳐 구현 완료 (2026-04-29). 83/83 테스트 통과. 모든 그룹 master merge 완료.**

| 그룹 | 플랜 파일 | 브랜치 | 상태 |
|------|-----------|--------|------|
| A — 프롬프트 관리 강화 | `docs/superpowers/plans/2026-04-29-group-a-prompt-management.md` | `feature/group-a` | 완료 |
| C — 운영/모니터링 | `docs/superpowers/plans/2026-04-29-group-c-health-monitoring.md` | `feature/group-c` | 완료 |
| D — RAG mode 파라미터화 | `docs/superpowers/plans/2026-04-29-group-d-rag-mode.md` | `feature/group-d` | 완료 |
| B — Job 관리 강화 | `docs/superpowers/plans/2026-04-29-group-b-job-management.md` | `feature/group-b` | 완료 |

1. `.env` 없으면 `.env.example` 복사 후 Hostinger `DATABASE_URL` 설정
2. `pytest tests/ -x` 로 현재 상태 확인

## 개요

Oracle PL/SQL + 딕셔너리 + 정책 문서를 v2 canonical 식별자 markdown으로 역문서화하는 비동기 FastAPI 서비스 (port 8004). LightRAG context 조회 → LLM 생성 → 품질 검증 (최대 3회 재시도) → ingestion-router callback.

## 제약 사항

- **AST / 결정론적 코드 분석 파이프라인 투입 금지** — hint 추출은 prefix 정규식만. RAG+LLM 컨셉이 깨짐
- **정규식에 `\b` 워드 바운더리 사용 금지** — Python `\b`는 한국어 조사(은/는/을/를)를 단어 경계로 인식 못 함. 대신 `(?<![A-Z0-9_])...(?![A-Z0-9_])` 패턴 사용 (validator.py에서 실증됨)
- **LightRAG insert 금지** — 이 서비스는 query-only. insert는 ingestion-router가 callback 수신 후 담당
- **역문서 표준 변경 금지** — `docs/standard.md` 기준 v2 표준. 표기 규칙은 그래프 형성의 핵심
- **로컬 DB 없음** — DATABASE_URL = Hostinger 원격 PostgreSQL 전용. 단위 테스트는 InMemoryJobStore 사용
- **check 3/4 구현 금지** — regex로 enum 표기/컬럼 점 표기 강제 시 false positive 누적 불가피 (Oracle exception명, OUT파라미터 대입값 등). 표기 규칙은 프롬프트로 유도, validator는 check 1–2만
- **check 5 구현 금지** — false positive 위험으로 의도적 제외

## 준수 사항

- `source_hash = sha256(source_bytes + prompt_version.encode())` — 동일 콘텐츠+프롬프트 조합은 캐시 히트
- RAG 조회 실패 시 빈 컨텍스트로 계속 진행 + WARN 로그 (job 중단 금지)
- 재시도 시 구체적 실패 메시지를 LLM에 전달 (예: `"check 1 실패: TBL_LOAN_APPLICATION 누락"`)
- `ADMIN_API_KEY` 미설정 시 인증 비활성 — Forge `auth.py` 패턴 동일 적용
- Forge 패턴 준수 — `_safe_process` 래퍼, async job store, `verify_api_key` factory
- `test_config_defaults`는 `.env` 파일 존재 시 깨짐 — `monkeypatch.delenv` + `Config(_env_file=None)` 조합 사용
- 프롬프트 DB 업데이트는 `PUT /admin/prompts/{asset_type}` — `seed_if_empty`는 최초 시드 전용, 기존 레코드 덮어쓰지 않음
- `/health` DB 판단은 `isinstance(store, PostgresJobStore)` 사용 — `_state["pool"]`은 lifespan 실패 시 None으로 남아 신뢰 불가 (Group C 실증)
- `admin.py` 내 `_safe_process`는 함수 내부 `from worker import` 방식 — 테스트 패치 시 `worker._safe_process` 대상으로 (Group B 실증)

## 스택

| 항목 | 선택 |
|------|------|
| 런타임 | Python 3.11+ |
| 프레임워크 | FastAPI + uvicorn |
| HTTP | httpx (async) |
| DB 드라이버 | asyncpg + PostgreSQL (Hostinger 원격) |
| 설정 | pydantic-settings |
| 테스트 | pytest + pytest-asyncio |
| 포트 | 8004 |

## 구조

| 파일/디렉토리 | 역할 |
|------|------|
| `config.py` | 환경변수 (pydantic-settings) |
| `models.py` | Pydantic 모델 (Job: source_bytes/rag_mode 포함, JobStatus, AssetType) |
| `job_store.py` | JobStore ABC + InMemoryJobStore + PostgresJobStore + PromptStore |
| `schema.sql` | DDL (rdoc_job, rdoc_prompt — IF NOT EXISTS, idempotent) |
| `auth.py` | `verify_api_key()` factory |
| `validator.py` | 역문서 품질 검증 check 1–2 (식별자 누락, 대소문자) |
| `llm_client.py` | OpenAI-compatible 비동기 클라이언트 (Semaphore 동시성 제한) |
| `rag_client.py` | LightRAG query-only 클라이언트 |
| `prompts.py` | PromptStore 초기 시드 (asset_type별) |
| `processor.py` | 파이프라인 오케스트레이터 |
| `callback.py` | ingestion-router 콜백 전송 (3회 retry) |
| `worker.py` | 비동기 워커 루프 + `_safe_process` |
| `app.py` | FastAPI 앱 (5 엔드포인트 + lifespan) |
| `admin.py` | 관리 API (8 엔드포인트, auth gated) — job 목록/retry/stats, 프롬프트 CRUD/히스토리/롤백 |
| `Dockerfile` | Docker 빌드 |
| `main.py` | uvicorn 진입점 |
| `tests/` | 단위 테스트 + Mock E2E (test_e2e.py) |
| `docs/standard.md` | v2 역문서 표준 (표기 규칙 기준) |
| `docs/superpowers/specs/2026-04-27-reverse-doc-service-design.md` | 설계 스펙 (초기 서비스) |
| `docs/superpowers/plans/2026-04-27-reverse-doc-service.md` | 구현 플랜 (15 Tasks, 완료) |
| `docs/superpowers/specs/2026-04-29-reverse-doc-feature-enhancements-design.md` | 추가 피쳐 설계 스펙 (Group A/B/C/D) |
| `docs/superpowers/plans/2026-04-29-group-a-prompt-management.md` | Group A 구현 플랜 |
| `docs/superpowers/plans/2026-04-29-group-c-health-monitoring.md` | Group C 구현 플랜 |
| `docs/superpowers/plans/2026-04-29-group-d-rag-mode.md` | Group D 구현 플랜 |
| `docs/superpowers/plans/2026-04-29-group-b-job-management.md` | Group B 구현 플랜 |
| `docs/simulation/` | 시뮬 자산 (PL/SQL, 딕셔너리, 정책, 역문서) |

## 하네스 진화 원칙

Task 실패 원인 발견 시 제약 사항에 이유 포함하여 즉시 추가. 성공한 비자명 패턴은 준수 사항에 추가.

## 완료 조건

```bash
pytest tests/ -v                        # 전체 테스트 통과 (83/83)
python main.py                          # port 8004 기동 확인
curl http://localhost:8004/health       # {"status":"ok","queue":{"queued":0,"processing":0}} 반환
```
