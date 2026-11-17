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


def graph_line(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("lines"), list) or len(payload["lines"]) != 1:
        raise GraphError("unexpected_lines")
    line = payload["lines"][0]
    if not isinstance(line, dict) or line.get("term") != TERM:
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


def adapt_graph(payload, fields: DocumentedFields, *, fictional=False):
    line = graph_line(payload)
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

    return {"source": "fictional_fixture" if fictional else "google_trends_research", "term": TERM,
            "geography": geography, "granularity": cadence, "points": points}
