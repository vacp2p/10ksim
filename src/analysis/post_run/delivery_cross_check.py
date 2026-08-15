"""Check a log-derived delivery number against the nodes' own received counter.

Delivery is counted from log lines, so anything the collector drops reads as a message
that was never delivered. The nodes also count receives themselves, in a counter that
does not go through the log pipeline, so the two disagreeing says the shortfall is
collection loss rather than a protocol failure. Believing either alone has burned us
both ways: a sub-100% number reported as a finding, and a real parser bug mistaken for
collector lag.
"""

import logging
from datetime import datetime
from typing import Optional

from pydantic import BaseModel
from result import Err, Ok

from src.analysis.metrics import scrape_utils

logger = logging.getLogger(__name__)

RECEIVED_METRIC = "libp2p_gossipsub_received_total"
TOLERANCE = 0.001
"""Fractional gap treated as rounding rather than loss."""


class DeliveryCrossCheck(BaseModel):
    from_logs: int
    from_counters: Optional[int]
    verdict: str
    detail: str


def _as_datetime(value) -> datetime:
    """Metadata carries the window as ISO strings; the query builder needs datetimes."""
    return value if isinstance(value, datetime) else datetime.fromisoformat(value)


def counter_deliveries(
    url: str, namespace: str, start: datetime, end: datetime, step: int = 60
) -> Optional[int]:
    """Total receives the nodes counted over the window, or None if unavailable."""
    start, end = _as_datetime(start), _as_datetime(end)
    query = f"sum(max_over_time({RECEIVED_METRIC}{{namespace='{namespace}'}}[{step}s]))"
    match scrape_utils.get_query_data(scrape_utils.create_promql(url, query, start, end, step)):
        case Ok(data):
            series = data["data"]["result"]
            values = [float(value) for point in series for _, value in point.get("values", [])]
            return int(max(values)) if values else None
        case Err(error):
            logger.warning(f"Could not read `{RECEIVED_METRIC}`: {error}")
            return None


def cross_check(from_logs: int, from_counters: Optional[int]) -> DeliveryCrossCheck:
    """Whether a delivery shortfall in the logs is real or an artefact of collection."""
    if from_counters is None:
        return DeliveryCrossCheck(
            from_logs=from_logs,
            from_counters=None,
            verdict="unverified",
            detail=f"{RECEIVED_METRIC} was not available, so the log count stands alone",
        )

    missing = from_counters - from_logs
    if missing <= from_counters * TOLERANCE:
        return DeliveryCrossCheck(
            from_logs=from_logs,
            from_counters=from_counters,
            verdict="confirmed",
            detail="the nodes' own counters agree with the logs",
        )

    return DeliveryCrossCheck(
        from_logs=from_logs,
        from_counters=from_counters,
        verdict="collection_loss",
        detail=(
            f"the nodes counted {missing} more receives than the logs show "
            f"({missing / from_counters:.2%} of deliveries), so delivery measured from logs "
            f"is a floor, not the protocol's result"
        ),
    )


def report(result: DeliveryCrossCheck) -> None:
    if result.verdict == "collection_loss":
        logger.warning(f"Delivery cross-check: {result.detail}")
    else:
        logger.info(f"Delivery cross-check ({result.verdict}): {result.detail}")
