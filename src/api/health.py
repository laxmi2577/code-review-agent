import os
import time
from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel

from src.config import get_settings

router = APIRouter(tags=["Health"])


class HealthResponse(BaseModel):
    status: str
    index_loaded: bool
    index_age_seconds: Optional[int] = None


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    settings = get_settings()
    index_path = settings.local_index_path
    index_loaded = os.path.exists(index_path)

    index_age_seconds = None
    if index_loaded:
        mtime = os.path.getmtime(index_path)
        index_age_seconds = int(time.time() - mtime)

    return HealthResponse(
        status="ok",
        index_loaded=index_loaded,
        index_age_seconds=index_age_seconds,
    )
