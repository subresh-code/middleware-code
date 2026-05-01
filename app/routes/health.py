from fastapi import APIRouter

router = APIRouter()

@router.get("/health", tags=["health"])
def health_check():
    """
    Health check endpoint used by developers,
    Docker, and future orchestration tools.
    """
    return {"status": "ok"}
