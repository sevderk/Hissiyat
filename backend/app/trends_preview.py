"""Owner-operated, one-query entry point for a local Trends preview."""

import argparse
import getpass
from http.client import HTTPConnection
import json
import logging
from pathlib import Path
import sys
from urllib.parse import urlsplit
import warnings

from app.core.config import Settings
from app.core.trends_research import TERM, DocumentedFields, GraphError, adapt_graph

HOST = "trends.googleapis.com"
DISCOVERY = f"https://{HOST}/$discovery/rest?version=v1beta"
MAX_BYTES = 1024 * 1024
SHAPE_FIELDS = frozenset({"lines", "term", "points", "date", "time", "timestamp", "startDate", "startTime",
                          "geo", "region", "regionCode", "geography", "granularity", "aggregation", "value",
                          "status", "valueStatus", "isMissing", "isSuppressed", "hasData", "metadata", "scale", "unit"})


class SingleSend:
    """Retain the bounded transport that successfully completed discovery."""

    def __init__(self, session):
        self.session = session
        self.sent = False
        self.rejected = False
        self.status = None

    def request(self, uri, method="GET", body=None, headers=None):
        from httplib2 import Response

        url = urlsplit(uri)
        if self.sent or url.scheme != "https" or url.netloc != HOST or url.fragment:
            self.rejected = True
            raise GraphError("transport_rejected")
        self.sent = True
        with send(self.session, uri, method, body, headers) as reply:
            self.status = reply.status_code
            content = read_body(reply) if 200 <= reply.status_code < 300 else b""
            return Response({"status": str(reply.status_code), "content-type": reply.headers.get("Content-Type", "")}), content


def send(session, uri, method, body, headers):
    return session.request(method, uri, data=body, headers=headers, timeout=20,
                           allow_redirects=False, stream=True)


def read_body(reply):
    content = bytearray()
    for chunk in reply.iter_content(chunk_size=16384):
        if len(content) + len(chunk) > MAX_BYTES:
            raise GraphError("response_too_large")
        content.extend(chunk)
    return bytes(content)


def allowed_query(uri):
    try:
        url = urlsplit(uri)
        return (
            url.scheme == "https" and url.hostname in (HOST, "www.googleapis.com")
            and url.port in (None, 443) and url.username is None and url.password is None and not url.fragment
        )
    except (TypeError, ValueError):
        return False


def single_graph(key):
    from googleapiclient.discovery import build
    from requests import Session
    from requests.adapters import HTTPAdapter

    with Session() as session:
        session.trust_env = False
        session.mount("https://", HTTPAdapter(max_retries=0))
        discovery = SingleSend(session)
        details = {"stage": "discovery", "query_attempted": False, "http_status": None}
        try:
            service = build("trends", "v1beta", developerKey=key, discoveryServiceUrl=DISCOVERY,
                            cache_discovery=False, num_retries=0, http=discovery)
        except Exception:
            return None, {**details, "reason": "transport_rejected" if discovery.rejected else "discovery_failed",
                          "discovery_attempted": discovery.sent, "http_status": discovery.status}
        details.update(stage="request", discovery_attempted=discovery.sent)
        try:
            operation = service.getGraph(terms=TERM)
            uri, method = operation.uri, operation.method
            body, headers = operation.body, operation.headers
        except AttributeError:
            return None, {**details, "reason": "operation_unavailable"}
        except Exception:
            return None, {**details, "reason": "request_construction_failed"}
        if not isinstance(uri, str) or method not in ("GET", "POST") or not allowed_query(uri):
            return None, {**details, "reason": "request_target_rejected"}

        # Send the official SDK's generated method, URI and parameters once. The
        # SDK's default httplib2 transport can resend after a malformed status line.
        details["query_attempted"] = True
        try:
            with send(session, uri, method, body, headers) as reply:
                details["http_status"] = reply.status_code
                if not 200 <= reply.status_code < 300:
                    return None, {**details, "reason": "request_http_error"}
                content = read_body(reply)
        except GraphError:
            return None, {**details, "reason": "response_too_large"}
        except Exception:
            return None, {**details, "reason": "request_network_or_transport_failed"}
        try:
            payload = json.loads(content)
        except (ValueError, UnicodeError):
            return None, {**details, "reason": "invalid_response_json"}
        return payload, {"discovery_attempted": discovery.sent, "query_attempted": True, "http_status": details["http_status"]}


def shape_summary(payload):
    def recognized(obj):
        return {name: type(obj[name]).__name__ for name in sorted(SHAPE_FIELDS & obj.keys())} if isinstance(obj, dict) else {}

    lines = payload.get("lines") if isinstance(payload, dict) else None
    line = lines[0] if isinstance(lines, list) and len(lines) == 1 else None
    points = line.get("points") if isinstance(line, dict) else None
    return {"root": recognized(payload), "line": recognized(line), "first_point": recognized(points[0]) if isinstance(points, list) and points else {},
            "point_count": len(points) if isinstance(points, list) else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fields", type=Path, help="Private local mapping verified against authenticated documentation")
    parser.add_argument("--status-file", type=Path, help="Optional new file for the same sanitized terminal result")
    args = parser.parse_args()

    def finish(status, code, **details):
        report = json.dumps({"status": status, **details})
        print(report, flush=True)
        if args.status_file is not None:
            try:
                with args.status_file.open("x", encoding="utf-8") as stream:
                    stream.write(report + "\n")
            except OSError:
                print('{"status":"status_file_unavailable"}', flush=True)
        return code

    if not sys.stdin.isatty() or sys.stdin is not sys.__stdin__:
        return finish("interactive_console_required", 2, query_attempted=False)
    logging.disable(logging.CRITICAL)
    HTTPConnection.debuglevel = 0
    stage = "configuration"
    result = {"query_attempted": False}
    try:
        settings = Settings()
        if settings.environment != "development":
            return finish("development_required", 2, query_attempted=False)
        fields = None
        if args.fields is not None:
            with args.fields.open("rb") as source:
                fields = DocumentedFields.model_validate_json(source.read(4097))
        stage = "key_input"
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            key = getpass.getpass("Google Trends API key (hidden, one approved career query): ")
        if not key or not key.isascii() or not key.isprintable() or any(c.isspace() for c in key):
            return finish("invalid_key_input", 2, query_attempted=False)
        stage = "client"
        payload, result = single_graph(key)
        del key
        if payload is None:
            return finish("stopped", 2, **result)
        stage = "response_validation"
        summary = shape_summary(payload)
        if fields is None:
            return finish("completed", 0, **result, structure=summary, display="withheld")
        try:
            preview = adapt_graph(payload, fields)
        except GraphError as failure:
            return finish("withheld", 2, **result, structure=summary, stage=stage, reason=str(failure))
        del payload
        stage = "preview_server"
        import uvicorn
        from app.main import create_app

        finish("ready", 0, **result, structure=summary, stage=stage)
        uvicorn.run(create_app(settings, trends_preview=preview), host="127.0.0.1", port=8058,
                    access_log=False, proxy_headers=False, log_config=None)
        return 0
    except (Exception, KeyboardInterrupt):
        return finish("stopped", 2, **{**result, "stage": stage})


if __name__ == "__main__":
    sys.exit(main())
