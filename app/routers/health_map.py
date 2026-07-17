from fastapi import APIRouter, Query
from app.services.health_engine import fetch_overview, fetch_entity_detail, fetch_domains

router = APIRouter(prefix="/health-map", tags=["HealthMap"])


@router.get("/api/domains")
def domains():
    return fetch_domains()


@router.get("/api/overview")
def overview(domain: str = Query(None, description="Filter by business domain")):
    return fetch_overview(domain=domain)


@router.get("/api/entity/{entity_id}")
def entity_detail(entity_id: int):
    data = fetch_entity_detail(entity_id)
    if data is None:
        return {"error": "Entity not found"}
    return data
