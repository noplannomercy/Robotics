# Robotics

Oracle PL/SQL 소스를 v2 canonical 식별자 markdown으로 역문서화하는 비동기 FastAPI 서비스.

## 개요

```
PL/SQL 소스 파일
    → LightRAG 컨텍스트 조회 (hint 키워드 기반)
    → LLM 역문서 생성 (최대 3회 재시도)
    → 품질 검증 (check 1: 식별자 누락, check 2: 대소문자)
    → LightRAG /documents/text callback (그래프 구축)
```

## 빠른 시작

```bash
# 의존성 설치
pip install -r requirements.txt

# 환경변수 설정
cp .env.example .env
# DATABASE_URL, LLM_API_KEY, LIGHTRAG_URL 설정

# 서버 기동
python main.py
# → http://localhost:8004
```

## API

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/health` | 상태 확인 |
| POST | `/jobs` | 역문서화 job 생성 |
| GET | `/jobs/{id}` | job 상태 조회 |
| GET | `/jobs/{id}/result` | 역문서 결과 조회 |
| DELETE | `/jobs/{id}` | job 삭제 |
| GET | `/admin/jobs` | job 목록 (auth) |
| POST | `/admin/jobs/{id}/retry` | job 재시도 (auth) |
| PUT | `/admin/prompts/{asset_type}` | 프롬프트 업데이트 (auth) |

### POST /jobs 예시

```bash
curl -X POST http://localhost:8004/jobs \
  -F "asset_type=plsql" \
  -F "file=@PKG_LOAN.sql" \
  -F "callback_url=http://lightrag-host:9621/documents/text"
```

응답:
```json
{"job_id": "uuid", "status": "queued"}
```

## 환경변수

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `LLM_URL` | OpenAI-compatible LLM endpoint | - |
| `LLM_MODEL` | 모델명 | - |
| `LLM_API_KEY` | API 키 | - |
| `LLM_TIMEOUT` | 타임아웃 (초) | 120 |
| `LLM_CONCURRENCY` | 동시 처리 수 | 3 |
| `LIGHTRAG_URL` | LightRAG 서버 URL | - |
| `DATABASE_URL` | PostgreSQL 연결 문자열 | - |
| `ADMIN_API_KEY` | 관리 API 키 (미설정 시 인증 비활성) | - |
| `MAX_FILE_SIZE_KB` | 업로드 최대 크기 | 200 |
| `PORT` | 포트 | 8004 |
| `CALLBACK_FIELD_MAP` | 콜백 payload 필드 매핑 JSON | `{}` |
| `CALLBACK_KEEP_UNMAPPED` | 매핑 없는 필드 유지 여부 | true |

### LightRAG 직접 연동 설정 (.env)

```env
CALLBACK_FIELD_MAP={"content":"text","file_name":"file_source"}
CALLBACK_KEEP_UNMAPPED=false
```

## 처리 순서 (그래프 품질 최적화)

LightRAG 그래프 품질을 위해 아래 순서를 준수한다:

```
1단계: 딕셔너리 / ERD / 정책 문서 → LightRAG에 먼저 주입
2단계: PL/SQL 소스 → POST /jobs (RAG hit 가능 상태에서 역문서화)
```

순서를 지키지 않으면 역문서가 컨텍스트 없이 생성되어 그래프 연결 품질 저하.

## 캐싱

동일 파일 + 동일 프롬프트 버전 조합은 `source_hash`로 캐시 히트.  
재처리 필요 시 `DELETE /jobs/{id}` 후 재제출.

## 테스트

```bash
pytest tests/ -v
```

## 스택

- Python 3.11+ / FastAPI / uvicorn
- asyncpg + PostgreSQL
- httpx (async HTTP)
- pydantic-settings
