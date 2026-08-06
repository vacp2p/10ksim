"""Post-run analysis for the network-partition scenario."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, List

import pandas as pd

from src.analysis.post_run.scenario_common import (
    Row,
    event_time,
    latency_summary,
    prepare,
    write_table,
)
from src.deployments.core.event_log import find_events

if TYPE_CHECKING:
    from src.deployments.experiments.libp2p.nimlibp2p import NimLibp2pExperiment

logger = logging.getLogger(__name__)


def per_message_reach(df: pd.DataFrame, heal: datetime, split: int) -> pd.DataFrame:
    """One row per message: reach on each side, publish time, and which phase it belongs to."""
    side = (df["ordinal"] >= split).map({False: "a", True: "b"})
    counts = (
        df.assign(side=side)
        .pivot_table(index="msgId", columns="side", values="ordinal", aggfunc="count")
        .reindex(columns=["a", "b"])
        .fillna(0)
        .astype(int)
    )
    counts["reach"] = counts["a"] + counts["b"]
    counts["sent"] = df.groupby("msgId")["sent"].min()
    counts["phase"] = (counts["sent"] > heal).map({False: "split", True: "healed"})
    return counts.sort_values("sent").reset_index()


def partition_table(df: pd.DataFrame, heal: datetime, split: int, num_nodes: int) -> List[Row]:
    """Contained while split, then reconverging to the whole network."""
    per_msg = per_message_reach(df, heal, split)
    under = per_msg[per_msg["phase"] == "split"]
    after = per_msg[per_msg["phase"] == "healed"]
    crossed = int(((under["a"] > 0) & (under["b"] > 0)).sum())
    full = after[after["reach"] >= num_nodes]

    # The messages before the first full-reach one are still in flight across the merge.
    if full.empty:
        reconverged = "no message reached the whole network after the heal"
    else:
        reconverged = f"{(full.iloc[0]['sent'] - heal).total_seconds():.0f}s"

    contained = int((under["reach"] == under[["a", "b"]].max(axis=1)).sum())
    return [
        (
            "delivery under the split, own half",
            "100% of that half",
            f"mean reach {under['reach'].mean():.1f} over {len(under)} messages, "
            f"{contained} contained to one side",
        ),
        ("delivery under the split, far half", "0", f"{crossed} of {len(under)} messages crossed"),
        ("time to reconverge after the heal", "under 10s on unshaped links", reconverged),
        (
            "delivery after reconvergence",
            "100% of all nodes",
            f"{len(full)} of {len(after)} messages reached all {num_nodes}",
        ),
        (
            "latency across the merge",
            "a brief tail spike, then back to baseline",
            latency_summary(df[df["sent"] > heal]),
        ),
    ]


def run_partition_analysis(experiment: "NimLibp2pExperiment") -> None:
    dump_dir, df = prepare(experiment)
    cfg = experiment.config
    log = experiment.events_log_path

    heal = event_time(find_events(log, {"event": "partition_heal"}))
    if heal is None:
        raise ValueError("Partition analysis needs partition_heal in the events log")

    # The applied event records the real split; the config fraction is only a fallback.
    applied = find_events(log, {"event": "partition_applied"})
    split = applied[-1]["side_a"] if applied else int(cfg.num_relay_nodes * cfg.partition_fraction)
    write_table(dump_dir, "partition_result", partition_table(df, heal, split, cfg.num_relay_nodes))
