"""Explicit, single-use public-source access on a development loopback server."""

import asyncio
import re

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import SecretStr, ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.requests import ClientDisconnect

from app.core.research import ANALYSIS_SOURCES, APPROVAL_SOURCES, MAX_BODY_BYTES, ResearchError, ResearchRequest, run_research

router = APIRouter()
LOOPBACK = re.compile(r"127\.0\.0\.1(?::[0-9]{1,5})?")


def get_approved_request(source: str, setting: SecretStr) -> ResearchRequest | None:
    try:
        scope = ResearchRequest.model_validate_json(setting.get_secret_value())
    except ValidationError:
        return None
    allow_analysis = not scope.analyze_discussion or source in ANALYSIS_SOURCES
    return scope if scope.source == source and source in APPROVAL_SOURCES and allow_analysis else None


def reply(status: int, payload: dict) -> JSONResponse:
    return JSONResponse(payload, status_code=status, headers={"Cache-Control": "no-store"})


@router.post("/local/research", include_in_schema=False)
async def local_research(request: Request):
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
                if len(body) + len(chunk) > MAX_BODY_BYTES:
                    return reply(413, {"code": "too_large"})
                body.extend(chunk)
        scope = ResearchRequest.model_validate_json(body)
        body.clear()
    except (ValidationError, ClientDisconnect, TimeoutError):
        return reply(400, {"code": "invalid_input"})

    if scope.analyze_discussion and scope.source not in ANALYSIS_SOURCES:
        return reply(403, {"code": "analysis_permission_unverified"})
    if scope.analyze_discussion and getattr(request.app.state, "text_analysis_busy", False):
        return reply(429, {"code": "busy"})
    if scope.source in APPROVAL_SOURCES:
        if request.app.state.approved_research != scope:
            return reply(403, {"code": "approval_required"})
        # Compare and consume without yielding, including when the upstream call fails.
        request.app.state.approved_research = None
    if scope.analyze_discussion:
        request.app.state.text_analysis_busy = True
    try:
        result = await run_in_threadpool(run_research, scope, model_directory=request.app.state.settings.local_analysis_model_dir)
        return reply(200, result)
    except ResearchError as exc:
        failure = {"code": exc.code}
        if exc.upstream_status is not None:
            failure["upstream_status"] = exc.upstream_status
        return reply(exc.status, failure)
    except Exception:
        return reply(502, {"code": "provider_unavailable"})
    finally:
        if scope.analyze_discussion:
            request.app.state.text_analysis_busy = False
