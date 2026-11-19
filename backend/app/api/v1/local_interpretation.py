"""Loopback-only model generation for the most recent server-held evidence."""

import asyncio
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.requests import ClientDisconnect

from app.api.v1.local_research import LOOPBACK, reply
from app.core.local_interpretation import InterpretationError, generate_interpretation

router = APIRouter()


class InterpretationInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    package_id: str = Field(pattern=r"[0-9a-f]{32}")
    language: Literal["tr", "en"]


@router.post("/local/interpretation", include_in_schema=False)
async def interpret(request: Request):
    headers = request.headers
    if (request.client is None or request.client.host != "127.0.0.1"
            or not LOOPBACK.fullmatch(headers.get("host", ""))
            or headers.get("x-hissiyat-local-research") != "1"
            or any(header in headers for header in ("origin", "sec-fetch-site", "forwarded", "x-forwarded-for", "x-real-ip"))):
        return reply(404, {"code": "not_found"})
    if (request.url.query or headers.get("content-type", "").partition(";")[0].strip().lower() != "application/json"
            or "content-encoding" in headers):
        return reply(400, {"code": "invalid_input"})
    try:
        body = bytearray()
        async with asyncio.timeout(5):
            async for chunk in request.stream():
                if len(body) + len(chunk) > 512:
                    return reply(413, {"code": "too_large"})
                body.extend(chunk)
        submission = InterpretationInput.model_validate_json(body)
    except (ValidationError, ClientDisconnect, TimeoutError):
        return reply(400, {"code": "invalid_input"})
    retained = getattr(request.app.state, "interpretation_evidence", None)
    if retained is None:
        return reply(409, {"code": "evidence_expired"})
    package = retained
    if submission.package_id != package.package_id:
        return reply(409, {"code": "evidence_expired"})
    if getattr(request.app.state, "text_analysis_busy", False):
        return reply(429, {"code": "busy"})
    request.app.state.text_analysis_busy = True
    try:
        result = await run_in_threadpool(generate_interpretation, package, submission.language,
                                         request.app.state.settings.local_interpretation_port)
        return reply(200, {**result, "evidence_package": package.model_dump()})
    except InterpretationError as error:
        status = 504 if error.code == "model_timeout" else 422 if error.code in ("unsupported_claim", "invalid_model_output") else 503
        return reply(status, {"code": error.code})
    except Exception:
        return reply(503, {"code": "model_unavailable"})
    finally:
        request.app.state.text_analysis_busy = False
