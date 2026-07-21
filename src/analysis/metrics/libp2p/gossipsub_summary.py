"""Reduce the gossipsub control/efficiency counter CSVs (dumped by the
`with_gossipsub_detail_metrics` scrape) into per-muxer report numbers.

These are monotonic counters, so per node the total over the run is the last value; the
mesh-health gauges reduce the same way, giving end-of-run state.
We aggregate the across-node median (the typical node) for each metric, and derive the
duplicate ratio (duplicates / delivered), the cleanest single "how efficient was the
mesh" number. Meant for the Shadow section, where the run is deterministic so the
counts are exact and comparable across versions.
"""

import logging
import re
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

# Relay pods are pod-0..pod-(N-1); this excludes the bootstrap and the publisher
# (named bootstrap-* / pod-api-requester-* on the cluster).
_RELAY_POD = re.compile(r"pod-\d+$")

logger = logging.getLogger(__name__)

# scrape folder (under the run's metrics dir) -> report label. Order is the table order.
GOSSIPSUB_DETAIL: Dict[str, str] = {
    "mesh-peers": "mesh peers",
    "topic-peers": "topic peers",
    "connections": "connections",
    "gossipsub/ihave-recv": "IHAVE received",
    "gossipsub/iwant-sent": "IWANT sent",
    "gossipsub/iwant-recv": "IWANT received",
    "gossipsub/graft-sent": "GRAFT sent",
    "gossipsub/graft-recv": "GRAFT received",
    "gossipsub/prune-sent": "PRUNE sent",
    "gossipsub/prune-recv": "PRUNE received",
    "gossipsub/received": "messages received",
    "gossipsub/duplicate": "duplicate messages",
    "gossipsub/idontwant-saved": "IDONTWANT saved",
}


def _per_node_totals(metrics_dir: Path, folder: str, muxer: str) -> Optional[pd.Series]:
    """Last value per relay node for one counter metric = its total over the run.
    Excludes the bootstrap and publisher hosts (only `pod-<n>` are relays)."""
    csv = metrics_dir / folder / muxer
    if not csv.exists():
        logger.warning(f"gossipsub summary: missing {csv}")
        return None
    df = pd.read_csv(csv, parse_dates=["Time"], index_col="Time")
    cols = [c for c in df.columns if _RELAY_POD.fullmatch(c)]
    if not cols:
        return None
    return df[cols].ffill().iloc[-1]


def summarize(metrics_dir: Path, muxer: str) -> Dict[str, float]:
    """Across-node median of the per-node totals for each gossipsub detail metric,
    plus the duplicate ratio. `metrics_dir` is the run's `metrics/` dump."""
    totals: Dict[str, pd.Series] = {}
    summary: Dict[str, float] = {}
    for folder, label in GOSSIPSUB_DETAIL.items():
        series = _per_node_totals(metrics_dir, folder, muxer)
        if series is None or series.dropna().empty:
            continue
        totals[folder] = series
        summary[label] = round(float(series.median()), 1)

    recv = totals.get("gossipsub/received")
    dup = totals.get("gossipsub/duplicate")
    if recv is not None and dup is not None:
        ratio = (dup / recv.where(recv > 0)).dropna()
        if not ratio.empty:
            summary["duplicate ratio"] = round(float(ratio.median()), 3)
    return summary


def summary_table(metrics_dir: Path, muxers) -> pd.DataFrame:
    """A muxer-by-metric table of the medians, for the report / logs."""
    rows = {muxer: summarize(metrics_dir, muxer) for muxer in muxers}
    return pd.DataFrame(rows).reindex(list(GOSSIPSUB_DETAIL.values()) + ["duplicate ratio"])
