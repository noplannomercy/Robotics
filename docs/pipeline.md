# 역문서 파이프라인 (통합 KB 컨셉)

## 큰 그림

모든 시스템 자산을 같은 표준의 자연어 markdown으로 역문서화 → LightRAG 한 그래프에 모두 넣기 → 새 입력은 이 그래프를 retrieve해서 LLM 한 방.

```
[딕셔너리]   [ERD]    [업무 정책]   [API 명세]   [화면 명세]   ...
    │         │           │            │            │
    └─────────┴───────────┴────────────┴────────────┘
              ↓ (각자 표준대로 md 역문서화)
    ┌─────────────────────────────────────────┐
    │       LightRAG (단일 통합 그래프)        │
    └─────────────────┬───────────────────────┘
                      ↓
            [PL/SQL 패키지] → retrieve → LLM 한 방 → 역문서 → 같은 그래프에 insert
```

## 핵심 컨셉

- **모든 입력 = 자연어 + canonical 식별자**
- **결정론적 코드 분석(AST/식별자 스캔) 일절 안 함** — 그게 들어오면 "AST 라이트"가 되고 컨셉이 깨짐
- **LLM이 소스 직접 이해 + RAG 컨텍스트로 표준대로 작성**
- **LightRAG entity merging이 자산 간 식별자를 자동 결합** (딕셔너리의 `TBL_X` ↔ ERD의 `TBL_X` ↔ PL/SQL 역문서의 `TBL_X` = 한 노드)

## 변환 엔진 (자산 공통)

```python
async def to_reverse_doc(raw_input: str, asset_type: str) -> str:
    # 1. 키워드 hint로 RAG retrieve (단순 정규식 추출, 코드 분석 X)
    hint = extract_hint_keywords(raw_input)
    
    context = await rag.aquery(
        query=hint,
        param=QueryParam(mode="mix", only_need_context=True),
    )
    
    # 2. LLM 한 방 (식별자 추출/매핑/관계 파악 다 LLM)
    reverse = await llm.acomplete(
        system=STANDARD_PROMPTS[asset_type],   # 자산별 프롬프트
        user=f"[원문]\n{raw_input}\n\n[참조 컨텍스트]\n{context}",
    )
    
    # 3. 검증 (얇게 — 식별자 누락/표기 검사만)
    if not validate(raw_input, reverse):
        # 재생성 max 3회
        ...
    
    # 4. LightRAG insert
    await rag.ainsert(reverse)
    return reverse
```

`STANDARD_PROMPTS`는 95% 공통 (원칙·표기 규칙·예시). 자산별 차이는 단위 헤더와 단락 구성 가이드 정도.

## 도입 순서 (안정적인 자산부터 쌓기)

1. **딕셔너리** — 가장 안정. 모든 코드의 기반 entity (TBL/컬럼/FK/PK)
2. **ERD** — 딕셔너리 위에 TBL 간 관계 entity 추가
3. **업무 정책** — 도메인 의미 entity (이미 일부 보유)
4. **API/화면 명세 등 도메인 문서**
5. **PL/SQL 역문서** — 위 4개 다 retrieve해서 풍부한 컨텍스트로 생성

매 단계마다 그래프가 풍부해지면서 다음 단계 retrieve 품질이 올라감.

## LightRAG 청킹 규칙 (Docling HybridChunker 통합)

마크다운 `##` 헤더 = 청크 경계. 한 청크 = 한 단위 (PROC/TBL/정책 등).

```python
from io import BytesIO
from lightrag import LightRAG
from docling.document_converter import DocumentConverter
from docling.datamodel.base_models import DocumentStream
from docling_core.transforms.chunker import HybridChunker
from transformers import AutoTokenizer

TOKENIZER = AutoTokenizer.from_pretrained("BAAI/bge-m3")  # 임베딩 모델과 일치
CHUNKER   = HybridChunker(tokenizer=TOKENIZER, max_tokens=1024, merge_peers=True)
CONVERTER = DocumentConverter()

def docling_chunking_func(
    content: str,
    split_by_character: str | None = None,
    split_by_character_only: bool = False,
    chunk_token_size: int = 1024,
    chunk_overlap_token_size: int = 0,
    tiktoken_model: str = "gpt-4o",
) -> list[dict]:
    stream = DocumentStream(name="doc.md", stream=BytesIO(content.encode("utf-8")))
    doc = CONVERTER.convert(stream).document

    out = []
    for chunk in CHUNKER.chunk(doc):
        text = CHUNKER.contextualize(chunk)   # 헤더 prepend → entity extraction 강화
        out.append({"content": text, "tokens": len(TOKENIZER.encode(text))})
    return out

rag = LightRAG(
    working_dir="./kb",
    llm_model_func=...,
    embedding_func=...,
    chunking_func=docling_chunking_func,
)
```

**주의사항**:
- LightRAG 버전별 chunking_func 시그니처 차이 — 적용 전 본인 버전의 default chunker 시그니처 매칭 필수
- HybridChunker 토크나이저와 임베딩 토크나이저 일치 권장
- `contextualize()` 사용 (chunk.text 아님) — 헤더 컨텍스트 보존이 핵심

## 검증 (얇은 운영 안전망)

코드 분석 X, 출력 품질 검사만:

```python
def validate(raw: str, reverse: str) -> bool:
    raw_ids = set(re.findall(r'\b[A-Z][A-Z0-9_]+\b', raw))
    rev_ids = set(re.findall(r'\b[A-Z][A-Z0-9_]+\b', reverse))
    
    # 1. 누락 검사
    missing = raw_ids - rev_ids
    if missing: return False
    
    # 2. canonical 표기 (대문자 underscore) 일관성
    # 3. 코드값 enum이 'TBL.컬럼 = '값'' 형태인지
    # 4. 컬럼명 단독 등장 없는지
    
    return True
```

검증 실패 시 LLM에 피드백("이 식별자 누락", "이 표기 위반")해서 재생성. 3회 실패 → 사람 큐.

## 멱등성

패키지 소스 hash 저장. 미변경이면 skip.

## 향후 확장

- Java/Python/JS 등 다른 언어 코드 → 같은 컨셉으로 역문서화
- 같은 LightRAG 그래프에 모두 들어가면 시스템 전체가 하나의 의미 그래프
- 새 자산 종류 추가 시 표준 프롬프트만 추가하면 끝, 엔진 동일
