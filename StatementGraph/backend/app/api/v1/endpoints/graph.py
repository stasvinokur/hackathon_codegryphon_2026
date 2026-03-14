from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db_session
from app.schemas.graph import GraphEdge, GraphNode, GraphResponse
from app.services.graph.graph_builder import GraphBuilderService

router = APIRouter()


@router.get("/alert/{alert_id}", response_model=GraphResponse)
def graph_for_alert(alert_id: UUID, session: Session = Depends(get_db_session)) -> GraphResponse:
    service = GraphBuilderService(session)
    payload = service.graph_for_alert(alert_id)
    return GraphResponse(
        nodes=[GraphNode(**node) for node in payload.nodes],
        edges=[GraphEdge(**edge) for edge in payload.edges],
    )


@router.get("/merchant/{merchant_id}", response_model=GraphResponse)
def graph_for_merchant(merchant_id: str, session: Session = Depends(get_db_session)) -> GraphResponse:
    service = GraphBuilderService(session)
    payload = service.graph_for_merchant(merchant_id)
    return GraphResponse(
        nodes=[GraphNode(**node) for node in payload.nodes],
        edges=[GraphEdge(**edge) for edge in payload.edges],
    )
