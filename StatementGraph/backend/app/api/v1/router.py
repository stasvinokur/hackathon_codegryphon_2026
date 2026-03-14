from fastapi import APIRouter

from app.api.v1.endpoints import (
    alerts,
    graph,
    health,
    merchant_resolution,
    statements,
    transactions,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(statements.router, prefix="/statements", tags=["statements"])
api_router.include_router(transactions.router, prefix="/transactions", tags=["transactions"])
api_router.include_router(alerts.router, prefix="/alerts", tags=["alerts"])
api_router.include_router(graph.router, prefix="/graph", tags=["graph"])
api_router.include_router(
    merchant_resolution.router,
    prefix="/merchant-resolution",
    tags=["merchant-resolution"],
)
