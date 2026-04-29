# Robotics 설치 매뉴얼

> 포트: 8004 | 역할: Oracle PL/SQL → v2 canonical markdown 역문서화 비동기 서비스

---

## 1. 사전 조건

- Docker, Docker Compose 설치
- 외부 PostgreSQL 접근 가능 (Hostinger DB)
- LightRAG 서비스 접근 가능
- OpenAI-compatible LLM API 키

---

## 2. 설치

```bash
# 1. 클론
git clone https://github.com/noplannomercy/Robotics.git
cd Robotics

# 2. 환경변수 설정
cp .env.example .env
vi .env
```

### .env 필수 항목

| 변수 | 설명 | 예시 |
|------|------|------|
| `DATABASE_URL` | Hostinger PostgreSQL DSN | `postgresql://user:pass@host:5432/dbname` |
| `LLM_URL` | LLM API 엔드포인트 | `https://api.openai.com/v1/chat/completions` |
| `LLM_MODEL` | 모델명 | `gpt-4o` |
| `LLM_API_KEY` | LLM API 키 | `sk-...` |
| `LIGHTRAG_URL` | LightRAG 서비스 URL | `http://localhost:9621` |
| `LIGHTRAG_API_KEY` | LightRAG API 키 | |
| `ADMIN_API_KEY` | 관리 API 인증 키 (미설정 시 비활성) | |

```bash
# 3. 빌드 + 기동
docker compose up -d --build

# 4. 헬스체크
curl http://localhost:8004/health
# 예상: {"status":"ok","queue":{"queued":0,"processing":0}}
```

> DB 스키마(`rdoc_job`, `rdoc_prompt`)는 기동 시 자동 생성됨 (CREATE IF NOT EXISTS).

---

## 3. 주요 명령어

```bash
# 로그 확인
docker compose logs -f robotics

# 재시작
docker compose restart robotics

# 재빌드 후 교체
docker compose up -d --build

# 정지
docker compose down
```

---

## 4. 트러블슈팅

| 증상 | 원인 | 조치 |
|------|------|------|
| `/health` → `{"status":"degraded"}` | DB 연결 실패 | `DATABASE_URL` 확인 |
| 역문서화 결과 없음 | LightRAG 연결 실패 | `LIGHTRAG_URL` 확인 (빈 컨텍스트로 계속 진행됨) |
| LLM 호출 실패 | API 키/URL 오류 | `LLM_API_KEY`, `LLM_URL` 확인 |
| 프롬프트 없음 오류 | DB에 초기 프롬프트 미시드 | `POST /admin/prompts/seed` 호출 |
