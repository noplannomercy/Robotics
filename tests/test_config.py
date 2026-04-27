# tests/test_config.py
import pytest
from config import Config


def test_config_defaults(monkeypatch):
    for key in ["LLM_URL", "LLM_MODEL", "LLM_API_KEY", "LLM_TIMEOUT", "LLM_CONCURRENCY",
                "LIGHTRAG_URL", "LIGHTRAG_API_KEY", "RAG_TIMEOUT",
                "DATABASE_URL", "ADMIN_API_KEY", "MAX_FILE_SIZE_KB", "HOST", "PORT"]:
        monkeypatch.delenv(key, raising=False)
    config = Config(_env_file=None)
    assert config.llm_url == "http://localhost:11434/v1/chat/completions"
    assert config.llm_model == "qwen2.5:14b"
    assert config.llm_api_key == ""
    assert config.llm_timeout == 120
    assert config.llm_concurrency == 3
    assert config.lightrag_url == "http://localhost:8080"
    assert config.lightrag_api_key == ""
    assert config.rag_timeout == 60
    assert config.database_url == ""
    assert config.admin_api_key == ""
    assert config.max_file_size_kb == 200
    assert config.host == "0.0.0.0"
    assert config.port == 8004


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("LLM_URL", "http://custom:8080/v1/chat/completions")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")
    monkeypatch.setenv("LLM_TIMEOUT", "60")
    monkeypatch.setenv("LLM_CONCURRENCY", "5")
    monkeypatch.setenv("RAG_TIMEOUT", "30")
    monkeypatch.setenv("PORT", "9000")
    config = Config()
    assert config.llm_url == "http://custom:8080/v1/chat/completions"
    assert config.llm_model == "gpt-4o"
    assert config.llm_timeout == 60
    assert config.llm_concurrency == 5
    assert config.rag_timeout == 30
    assert config.port == 9000
