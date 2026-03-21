from fastapi import APIRouter

from app.api.deps import route_repo
from app.models.domain import IntegrationRoute
from app.schemas.unified import IntegrationRouteIn

router = APIRouter()


@router.get("/v1/routes")
async def list_routes():
    return await route_repo.list_routes()


@router.post("/v1/routes", status_code=201)
async def upsert_route(payload: IntegrationRouteIn):
    route = IntegrationRoute(**payload.model_dump(by_alias=False))
    await route_repo.upsert_route(route)
    return route
