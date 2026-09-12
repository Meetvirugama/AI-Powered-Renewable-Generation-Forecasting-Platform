from fastapi import Header, HTTPException
from typing import Optional
from backend.core.config import get_settings

def verify_api_key(x_api_key: Optional[str] = Header(None)) -> bool:
    """FastAPI dependency to verify the provided API key against the configured one."""
    settings = get_settings()
    if not x_api_key or x_api_key != settings.pipeline_api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key"
        )
    return True
