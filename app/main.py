from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.health import router as health_router
from app.api.routes.routes import router as routes_router
from app.api.routes.unified import router as unified_router

app = FastAPI(title="Unified FastGPT-Dify API", version="0.1.0")

# Allow browser-based UIs (e.g., local Next.js) to call this gateway directly.
# In production, restrict origins to your domains.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(routes_router)
app.include_router(unified_router)
