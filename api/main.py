"""
FastAPI application factory.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.analysis import router as analysis_router
from api.routes.auth import router as auth_router


def create_app() -> FastAPI:
    application = FastAPI(
        title="Tennis Coach API",
        description="AI-powered tennis video analysis backend.",
        version="1.0.0",
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

    return application


app = create_app()
