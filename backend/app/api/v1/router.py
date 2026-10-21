"""Aggregate router for API v1."""

from fastapi import APIRouter

from app.api.v1.routers import agents, auth, providers, runs, system, tools, workspaces

api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(auth.router)
api_router.include_router(workspaces.router)
api_router.include_router(agents.router)
api_router.include_router(providers.router)
api_router.include_router(runs.router)
api_router.include_router(tools.router)

__all__ = ["api_router"]
