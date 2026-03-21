from app.models.domain import IntegrationRoute
from typing import Optional


class RouteRepository:
    def __init__(self):
        self._routes: dict[str, IntegrationRoute] = {}

    @staticmethod
    def _key(tenant_id: str, request_type: str) -> str:
        return f"{tenant_id}:{request_type}"

    async def get_route(self, tenant_id: str, request_type: str) -> Optional[IntegrationRoute]:
        route = self._routes.get(self._key(tenant_id, request_type))
        if route and route.enabled:
            return route
        return None

    async def list_routes(self) -> list[IntegrationRoute]:
        return list(self._routes.values())

    async def upsert_route(self, route: IntegrationRoute):
        self._routes[self._key(route.tenant_id, route.request_type)] = route
