import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from src.api.feedback import router as feedback_router
from src.api.health import router as health_router
from src.api.reviews import router as reviews_router
from src.api.webhooks import router as webhooks_router
from src.config import get_settings
from src.utils.logging import request_id_ctx, setup_logging


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        req_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        token = request_id_ctx.set(req_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = req_id
            return response
        finally:
            request_id_ctx.reset(token)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    setup_logging(log_level=settings.log_level)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="CodeLens",
        description="Retrieval-Augmented Code Review Agent with Codebase-Aware Context",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIdMiddleware)

    app.include_router(health_router)
    app.include_router(webhooks_router)
    app.include_router(feedback_router)
    app.include_router(reviews_router)

    @app.get("/", tags=["Root"])
    def root_endpoint():
        return {
            "name": "CodeLens",
            "version": "0.1.0",
            "status": "online",
            "docs": "/docs",
            "health": "/health",
        }

    return app


app = create_app()
