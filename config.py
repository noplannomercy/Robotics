from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    # LLM
    llm_url: str = "http://localhost:11434/v1/chat/completions"
    llm_model: str = "qwen2.5:14b"
    llm_api_key: str = ""
    llm_timeout: int = 120
    llm_concurrency: int = 3

    # LightRAG (쿼리 전용)
    lightrag_url: str = "http://localhost:8080"
    lightrag_api_key: str = ""
    rag_timeout: int = 60

    # 서비스
    database_url: str = ""
    admin_api_key: str = ""
    max_file_size_kb: int = 200
    host: str = "0.0.0.0"
    port: int = 8004

    # Callback payload 필드명 rename (Forge CALLBACK_FIELD_MAP과 동일)
    # 예: '{"content":"text","file_name":"file_source"}' → LightRAG /documents/text 형식
    callback_field_map: str = ""
    callback_keep_unmapped: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
