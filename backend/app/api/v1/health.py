from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel

from app.core.database import Database

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    """Report application liveness without checking external dependencies."""
    return HealthResponse()


class ReadinessResponse(BaseModel):
    status: Literal["ready", "unavailable"]
    database: Literal["ok", "unavailable"]


def get_database(request: Request) -> Database | None:
    return getattr(request.app.state, "database", None)


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
)
def get_readiness(
    response: Response,
    database: Annotated[Database | None, Depends(get_database)],
) -> ReadinessResponse:
    if database is None or not database.check_connection():
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessResponse(status="unavailable", database="unavailable")
    return ReadinessResponse(status="ready", database="ok")
