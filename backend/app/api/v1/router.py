"""Aggregate router for API v1."""

from fastapi import APIRouter

from app.api.v1.routers import auth, system, workspaces

api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(auth.router)
api_router.include_router(workspaces.router)

__all__ = ["api_router"]
