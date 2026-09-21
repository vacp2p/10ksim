"""Post-run analysis for the network-partition scenario."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, List, Tuple

import pandas as pd

from src.analysis.post_run.scenario_common import (
    Row,
    event_time,
    latency_summary,
    prepare,
    published_messages,
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


def split_outcomes(under: pd.DataFrame, split: int, num_nodes: int) -> Tuple[int, int, int]:
    """Messages under the split that reached their whole half, part of it, or both halves.

    The half a message landed in stands in for the one it was meant for: the publisher's
    entry side is not recorded. Undelivered messages have no row here and are counted apart.
    """
    crossed = (under["a"] > 0) & (under["b"] > 0)
    own = under["a"].where(under["a"] > 0, under["b"])
    own_size = (under["a"] > 0).map({True: split, False: num_nodes - split})
    full = ~crossed & (own == own_size)
    partial = ~crossed & (own < own_size)
    return int(full.sum()), int(partial.sum()), int(crossed.sum())


def partition_table(
    df: pd.DataFrame, heal: datetime, split: int, num_nodes: int, num_messages: int
) -> List[Row]:
    """Contained while split, then reconverging to the whole network."""
    per_msg = per_message_reach(df, heal, split)
    under = per_msg[per_msg["phase"] == "split"]
    after = per_msg[per_msg["phase"] == "healed"]
    full_own, partial_own, crossed = split_outcomes(under, split, num_nodes)
    undelivered = num_messages - per_msg["msgId"].nunique()
    full = after[after["reach"] >= num_nodes]

    # The messages before the first full-reach one are still in flight across the merge.
    if full.empty:
        reconverged = "no message reached the whole network after the heal"
    else:
        reconverged = f"{(full.iloc[0]['sent'] - heal).total_seconds():.0f}s"

    return [
        (
            "delivery under the split, own half",
            "100% of that half",
            f"{full_own} of {len(under)} messages reached their whole half, "
            f"{partial_own} reached only part of it",
        ),
        ("delivery under the split, far half", "0", f"{crossed} of {len(under)} messages crossed"),
        (
            "messages nobody received, whole run",
            "0",
            f"{undelivered} of {num_messages} published "
            "(no publish time recorded, so the phase is unknown)",
        ),
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
    write_table(
        dump_dir,
        "partition_result",
        partition_table(df, heal, split, cfg.num_relay_nodes, published_messages(experiment)),
    )
