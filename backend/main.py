"""FastAPI application entrypoint for the customer-support chatbot API.

Composition root for the HTTP surface: builds the app, enables CORS for the POC frontend
origins (from settings), registers the ``/session``, ``/chat``, and ``/report`` routes, and
calls ``init_tracing(settings)`` once at startup so the active tracer is registered before
any request is served. Run with ``uvicorn backend.main:app``.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import router
from backend.config.settings import get_settings
from backend.tracing.setup import init_tracing


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Register the active tracer at startup (no-op unless tracing is enabled/configured)."""
    init_tracing(get_settings())
    yield


def create_app() -> FastAPI:
    """Build and configure the FastAPI app (CORS + routes + tracing lifespan).

    Every route and the docs endpoints are mounted under ``settings.api_prefix`` (e.g.
    ``/api``) when set, so the app can sit behind a path-based reverse proxy that forwards
    ``/api/*`` without stripping the prefix. Empty prefix (the default) serves at root.
    """
    settings = get_settings()
    prefix = settings.normalized_api_prefix
    app = FastAPI(
        title="Customer Support Chatbot API",
        lifespan=lifespan,
        docs_url=f"{prefix}/docs",
        redoc_url=f"{prefix}/redoc",
        openapi_url=f"{prefix}/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router, prefix=prefix)
    return app


app = create_app()
