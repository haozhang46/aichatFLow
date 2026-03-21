from app.schemas.unified import UnifiedRequest
from app.services.routes_repo import RouteRepository


class RoutingService:
    def __init__(self, repo: RouteRepository):
        self.repo = repo

    async def resolve(self, req: UnifiedRequest):
        route = await self.repo.get_route(req.tenant_id, req.request_type)
        if not route:
            raise ValueError(f"No route found for tenant={req.tenant_id} type={req.request_type}")
        return route
