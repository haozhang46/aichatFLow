from fastapi import APIRouter

router = APIRouter()


@router.get("/v1/health")
async def health():
    return {"ok": True, "providers": ["fastgpt", "dify"]}
