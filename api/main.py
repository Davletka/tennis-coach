"""
FastAPI application factory with lifespan-managed DB pool.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import db
from api.routes.analysis import router as analysis_router
from api.routes.auth import router as auth_router
from api.routes.history import router as history_router
from api.settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_pool(settings.database_url)
    yield
    await db.close_pool()


def create_app() -> FastAPI:
    application = FastAPI(
        title="Tennis Coach API",
        description="AI-powered tennis video analysis backend.",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Allow all origins in development; tighten in production via env var if needed.
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(analysis_router)
    application.include_router(auth_router)
    application.include_router(history_router)

    return application


app = create_app()
