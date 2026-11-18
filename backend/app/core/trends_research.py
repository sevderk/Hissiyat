"""Bounded detection and adaptation of one owner-authorized Trends graph."""

from datetime import date, timedelta
import math
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TERM = "career"
MAX_POINTS = 2000
CADENCES = ("daily", "weekly", "monthly", "yearly")
DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
GEO = re.compile(r"(?:worldwide|[A-Z]{2}(?:-[A-Z0-9]{1,3})?)")


class GraphError(ValueError):
    """Messages are fixed and contain no response material."""


class DocumentedFields(BaseModel):
    """Field mapping from the owner's authenticated docs, never guessed from data."""

    model_config = ConfigDict(extra="forbid", strict=True)

    geography: str = Field(min_length=1, max_length=64)
    cadence: str = Field(min_length=1, max_length=64)
    date: str = Field(min_length=1, max_length=64)
    value: str = Field(min_length=1, max_length=64)
    status: str = Field(min_length=1, max_length=64)
    statuses: dict[str, Literal["observed", "missing", "suppressed"]] = Field(min_length=1, max_length=3)


class SummaryContract(DocumentedFields):
    """Operator-confirmed provider documentation and permission for local summaries."""

    measurement: Literal["consistently_scaled_search_interest"]
    display: Literal["local_summary"]


def graph_line(payload, term=TERM):
    if not isinstance(payload, dict) or not isinstance(payload.get("lines"), list) or len(payload["lines"]) != 1:
        raise GraphError("unexpected_lines")
    line = payload["lines"][0]
    if not isinstance(line, dict) or line.get("term") != term:
        raise GraphError("unexpected_term")
    points = line.get("points")
    if not isinstance(points, list) or not 0 < len(points) <= MAX_POINTS or not all(isinstance(p, dict) for p in points):
        raise GraphError("unexpected_points")
    return line


def _period_date(value):
    if not isinstance(value, str) or not DATE.fullmatch(value):
        raise GraphError("invalid_period_start")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise GraphError("invalid_period_start") from None


def _next(previous, current, cadence):
    if cadence == "daily" or cadence == "weekly":
        return (current - previous) == timedelta(days=1 if cadence == "daily" else 7)
    if cadence == "monthly":
        return current.year * 12 + current.month == previous.year * 12 + previous.month + 1
    return current.year == previous.year + 1


def adapt_graph(payload, fields: DocumentedFields, *, fictional=False, term=TERM):
    line = graph_line(payload, term)
    geography, cadence = line.get(fields.geography), line.get(fields.cadence)
    if not isinstance(geography, str) or not GEO.fullmatch(geography) or cadence not in CADENCES:
        raise GraphError("unknown_geography_or_cadence")
    if len({fields.geography, fields.cadence, "term", "points"}) != 4 or len({fields.date, fields.value, fields.status}) != 3:
        raise GraphError("overlapping_field_mapping")

    points = []
    previous = None
    for point in line["points"]:
        day = _period_date(point.get(fields.date))
        if ((cadence == "monthly" and day.day != 1) or (cadence == "yearly" and (day.month, day.day) != (1, 1))
                or (previous is not None and not _next(previous, day, cadence))):
            raise GraphError("invalid_period_sequence")
        raw_status = point.get(fields.status)
        status = fields.statuses.get(raw_status) if isinstance(raw_status, str) else None
        if status is None or fields.value not in point:
            raise GraphError("unverified_value_status")
        value = point[fields.value]
        if status == "observed":
            if (type(value) not in (int, float) or (type(value) is int and abs(value) > (2 ** 53 - 1))
                    or not math.isfinite(value)):
                raise GraphError("invalid_observed_value")
        elif value is not None:
            raise GraphError("unverified_gap_value")
        points.append({"date": day.isoformat(), "value": value, "status": status})
        previous = day

    return {"source": "fictional_fixture" if fictional else "google_trends_research", "term": term,
            "geography": geography, "granularity": cadence, "points": points}


def summarize_graph(series, *, geography, start_month, end_month):
    """Return derived findings only. Zero has ambiguous volume under the guide."""
    points = series["points"]
    first, last = points[0]["date"], points[-1]["date"]
    if series["geography"] != geography or first[:7] < start_month or last[:7] > end_month:
        raise GraphError("unverified_response_scope")
    observed = [point for point in points if point["status"] == "observed" and point["value"] != 0]
    if any(point["value"] < 0 for point in observed):
        raise GraphError("invalid_observed_value")
    peak = max((point["value"] for point in observed), default=None)
    peak_periods = [point["date"] for point in observed if point["value"] == peak]
    direction = "insufficient"
    if len(observed) >= 2:
        start, end = observed[0]["value"], observed[-1]["value"]
        direction = "increased" if end > start else "decreased" if end < start else "unchanged"
    return {
        "geography": geography, "cadence": series["granularity"],
        "first_period": first, "last_period": last, "nonzero": len(observed),
        "ambiguous_zero": sum(point["status"] == "observed" and point["value"] == 0 for point in points),
        "missing": sum(point["status"] == "missing" for point in points),
        "suppressed": sum(point["status"] == "suppressed" for point in points),
        "peak_period": peak_periods[0] if peak_periods else None, "peak_ties": len(peak_periods),
        "direction": direction,
    }
