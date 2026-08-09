"""Minimal Prometheus/VictoriaMetrics instant-query client.

Self-contained (stdlib only) so dst_dashboard doesn't depend on the 10ksim
analysis pipeline's scrape_utils for this dashboard-only feature.
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List

from result import Err, Ok, Result

logger = logging.getLogger(__name__)


def query_instant(
    base_url: str, query: str, timeout: int = 10
) -> Result[List[Dict[str, Any]], str]:
    """Execute a Prometheus/VictoriaMetrics instant query."""
    url = base_url + "query?query=" + urllib.parse.quote(query)

    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            status = response.status
            body = response.read().decode("utf-8")
    except urllib.error.URLError as e:
        return Err(f"request failed: {e}")

    if status != 200:
        return Err(f"status {status}: {body}")

    payload = json.loads(body)
    result = payload.get("data", {}).get("result", [])

    if not result:
        return Err("empty result")

    return Ok(result)
