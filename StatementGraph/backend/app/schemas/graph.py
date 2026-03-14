from __future__ import annotations

from pydantic import BaseModel


class GraphNode(BaseModel):
    data: dict


class GraphEdge(BaseModel):
    data: dict


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
