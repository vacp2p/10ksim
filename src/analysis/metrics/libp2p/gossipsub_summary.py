"""Reduce the gossipsub control/efficiency counter CSVs (dumped by the
`with_gossipsub_detail_metrics` scrape) into per-muxer report numbers.

Most of these are monotonic counters, so per node the total over the run is the last
value. The mesh-health gauges are not: they rise and fall, and the last sample lands
after publishing has stopped, where quic's connections have already decayed on idle. A
gauge is therefore reduced over the window instead, which is the state while traffic
was flowing.
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


# Gauges rise and fall, so the last sample is end-of-run state rather than the state
# under load. Everything else here is a monotonic counter.
GAUGES = frozenset({"mesh-peers", "topic-peers", "connections"})


def _per_node_values(metrics_dir: Path, folder: str, muxer: str) -> Optional[pd.Series]:
    """One value per relay node: a counter's total over the run, or a gauge's typical
    value across the window. Excludes bootstrap and publisher (only `pod-<n>` are relays)."""
    csv = metrics_dir / folder / f"{muxer}.csv"
    if not csv.exists():
        logger.warning(f"gossipsub summary: missing {csv}")
        return None
    df = pd.read_csv(csv, parse_dates=["Time"], index_col="Time")
    cols = [c for c in df.columns if _RELAY_POD.fullmatch(c)]
    if not cols:
        return None
    values = df[cols].ffill()
    if folder not in GAUGES:
        return values.iloc[-1]

    per_node = values.median()
    _warn_if_window_runs_past_traffic(folder, muxer, values, per_node)
    return per_node


def _warn_if_window_runs_past_traffic(
    folder: str, muxer: str, values: pd.DataFrame, per_node: pd.Series
) -> None:
    """A gauge that collapses inside the window drags the median below its value under
    load. The median survives a small tail but not a large one, and the result stays
    plausible while being wrong, so say so rather than let it pass silently."""
    over_time = values.median(axis=1)
    if over_time.empty or over_time.max() <= 0:
        return
    collapsed = (over_time < over_time.max() / 2).mean()
    if collapsed > 0.2:
        logger.warning(
            f"{folder} ({muxer}): {collapsed:.0%} of the scrape window sits below half the "
            f"peak, so the window runs past the traffic and this median ({per_node.median():.0f} "
            f"against a peak of {over_time.max():.0f}) understates the value under load"
        )


def summarize(metrics_dir: Path, muxer: str) -> Dict[str, float]:
    """Across-node median of the per-node totals for each gossipsub detail metric,
    plus the duplicate ratio. `metrics_dir` is the run's `metrics/` dump."""
    totals: Dict[str, pd.Series] = {}
    summary: Dict[str, float] = {}
    for folder, label in GOSSIPSUB_DETAIL.items():
        series = _per_node_values(metrics_dir, folder, muxer)
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
