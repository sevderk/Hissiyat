import asyncio
import re
from typing import Annotated, Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.requests import ClientDisconnect

from app.core.expression_signals import aggregate_expression_signals
from app.core.local_text_analysis import (
    MAX_BODY_BYTES, MAX_TEXT_CHARS, MAX_TEXTS, MIN_TEXTS, InsufficientVariation, analyze_texts,
)
from app.core.minilm import ModelUnavailable

router = APIRouter()
LOOPBACK_HOST = re.compile(r"127\.0\.0\.1(?::[0-9]{1,5})?")
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_TEXT_CHARS)]


class AnalysisInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)

    texts: list[Text] = Field(min_length=MIN_TEXTS, max_length=MAX_TEXTS, repr=False)
    k: int = Field(ge=2, le=3)
    method: Literal["nmf", "minilm", "both"] | None = None
    include_signals: bool = False


def reply(status: int, payload: dict) -> JSONResponse:
    return JSONResponse(payload, status_code=status, headers={"Cache-Control": "no-store"})


@router.post("/local/text-analysis", include_in_schema=False)
async def local_text_analysis(request: Request):
    headers = request.headers
    if (
        request.client is None or request.client.host != "127.0.0.1"
        or not LOOPBACK_HOST.fullmatch(headers.get("host", ""))
        or headers.get("x-hissiyat-local-analysis") != "1"
        or any(header in headers for header in ("origin", "sec-fetch-site", "forwarded", "x-forwarded-for", "x-real-ip"))
    ):
        return reply(404, {"code": "not_found"})
    if (request.url.query or headers.get("content-type", "").partition(";")[0].strip().lower() != "application/json"
            or "content-encoding" in headers):
        return reply(400, {"code": "invalid_input"})

    # Single worker for the opt-in endpoint. No queue of text-bearing requests.
    if getattr(request.app.state, "text_analysis_busy", False):
        return reply(429, {"code": "busy"})
    request.app.state.text_analysis_busy = True
    try:
        body = bytearray()
        async with asyncio.timeout(5):
            async for chunk in request.stream():
                if len(body) + len(chunk) > MAX_BODY_BYTES:
                    return reply(413, {"code": "too_large"})
                body.extend(chunk)
        submission = AnalysisInput.model_validate_json(body)
        body.clear()
        result = await run_in_threadpool(
            analyze_texts, submission.texts, submission.k, submission.method or "nmf",
            request.app.state.settings.local_analysis_model_dir,
        )
        if submission.include_signals:
            result["expression_signals"] = aggregate_expression_signals(submission.texts)
        elif submission.method is None:
            result = result["methods"]["nmf"]  # Keep the original NMF-only API shape for existing callers.
        return reply(200, result)
    except (ValidationError, ClientDisconnect, TimeoutError):
        return reply(400, {"code": "invalid_input"})
    except InsufficientVariation:
        return reply(422, {"code": "insufficient_variation"})
    except ModelUnavailable:
        return reply(503, {"code": "model_unavailable"})
    except Exception:
        # Do not log upstream exception messages or their text-bearing locals.
        return reply(503, {"code": "unavailable"})
    finally:
        request.app.state.text_analysis_busy = False
