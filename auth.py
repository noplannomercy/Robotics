from fastapi import Header, HTTPException

from config import Config


def verify_api_key(config: Config):
    """Admin API 키 인증 dependency. admin_api_key 미설정 시 인증 비활성."""
    def _verify(x_rdoc_key: str | None = Header(None)):
        if not config.admin_api_key:
            return None
        if x_rdoc_key != config.admin_api_key:
            raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return _verify
