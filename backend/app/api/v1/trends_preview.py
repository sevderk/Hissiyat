"""Read-only access to one in-memory Trends series on loopback."""

import re

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()
LOOPBACK = re.compile(r"127\.0\.0\.1(?::[0-9]{1,5})?")


@router.get("/local/trends-preview", include_in_schema=False)
async def trends_preview(request: Request):
    headers = request.headers
    valid = (
        request.client is not None and request.client.host == "127.0.0.1"
        and LOOPBACK.fullmatch(headers.get("host", ""))
        and headers.get("x-hissiyat-trends-preview") == "1" and not request.url.query
        and not any(header in headers for header in ("origin", "sec-fetch-site", "forwarded", "x-forwarded-for", "x-real-ip"))
    )
    return JSONResponse(
        request.app.state.trends_preview if valid else {"code": "not_found"},
        status_code=200 if valid else 404, headers={"Cache-Control": "no-store"},
    )
