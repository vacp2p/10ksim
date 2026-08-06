"""Post-run analysis for the node-churn scenario."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List, Optional, Sequence, Tuple

import pandas as pd

from src.analysis.post_run.scenario_common import (
    POD_COLUMN,
    Row,
    load_mesh_peers,
    mesh_peers_row,
    pct,
    prepare,
    write_table,
)
from src.deployments.core.event_log import find_events

if TYPE_CHECKING:
    from src.deployments.experiments.libp2p.nimlibp2p import NimLibp2pExperiment

logger = logging.getLogger(__name__)


def longest_run(mask: Sequence[bool]) -> Tuple[Optional[int], Optional[int], int]:
    """Start, end and length of the longest True stretch."""
    best = (None, None, 0)
    start = None
    for i, flag in enumerate(list(mask) + [False]):
        if flag and start is None:
            start = i
        elif not flag and start is not None:
            if i - start > best[2]:
                best = (start, i - 1, i - start)
            start = None
    return best


def churn_outages(df: pd.DataFrame, churned: Sequence[str]) -> pd.DataFrame:
    """Per churned node: the outage read off its own miss run, and what it missed after it.

    Pods keep serving past the scale-down and are back before the rollout finishes, so the
    scale-down window is not a node's outage; the stretch it missed is.
    """
    order = df.drop_duplicates("msgId").sort_values("sent")
    times = order["sent"].to_numpy()
    present = (
        df[df[POD_COLUMN].isin(set(churned))]
        .pivot_table(index=POD_COLUMN, columns="msgId", values="ordinal", aggfunc="size")
        .reindex(columns=order["msgId"])
        .notna()
    )

    rows = []
    for pod, got in present.iterrows():
        missed = ~got.to_numpy()
        start, end, length = longest_run(missed)
        after = [i for i, flag in enumerate(missed) if flag and end is not None and i > end]
        rows.append(
            {
                POD_COLUMN: pod,
                "missed": int(missed.sum()),
                "outage_messages": length,
                "outage_s": (
                    (times[end] - times[start]) / pd.Timedelta(seconds=1) if length else 0.0
                ),
                "missed_after": len(after),
                # How long the node keeps dropping messages once its main outage has ended.
                "recovery_tail_s": (
                    (times[after[-1]] - times[end]) / pd.Timedelta(seconds=1) if after else 0.0
                ),
            }
        )
    return pd.DataFrame(rows)


def churn_table(
    df: pd.DataFrame,
    churned: Sequence[str],
    num_messages: int,
    num_nodes: int,
    mesh: Optional[pd.DataFrame] = None,
) -> List[Row]:
    """Below 100%, with every miss inside the node's own outage."""
    is_churned = df[POD_COLUMN].isin(set(churned))
    survivors = num_nodes - len(set(churned))
    per_survivor = df[~is_churned].groupby(POD_COLUMN)["msgId"].nunique()
    out = churn_outages(df, churned)
    ragged = int((out["missed_after"] > 0).sum())

    return [
        (
            "delivery, whole run",
            "below 100%, and fully explained by the churn",
            pct(len(df), num_messages * num_nodes),
        ),
        (
            "delivery, nodes that stayed up",
            "100%",
            f"{per_survivor.min() if len(per_survivor) else 0} to "
            f"{per_survivor.max() if len(per_survivor) else 0} of {num_messages}, "
            f"on {len(per_survivor)} of {survivors} nodes",
        ),
        (
            "delivery, churned nodes",
            "one contiguous gap, nothing missed either side of it",
            f"missed {out['missed'].mean():.1f} of {num_messages} on average, "
            f"{out['outage_messages'].mean():.1f} in one stretch",
        ),
        (
            "clean recovery",
            "no misses once the node is back",
            f"{ragged} of {len(out)} nodes keep dropping after their outage, "
            f"worst {out['missed_after'].max()} messages over "
            f"{out['recovery_tail_s'].max():.0f}s",
        ),
        (
            "observed outage per churned node",
            "the configured downtime plus the drain and the rejoin dial stagger",
            f"{out['outage_s'].median():.0f}s median, {out['outage_s'].max():.0f}s worst",
        ),
        mesh_peers_row(mesh, "mesh peers after rejoin", pods=churned),
    ]


def run_churn_analysis(experiment: "NimLibp2pExperiment") -> None:
    dump_dir, df = prepare(experiment)
    cfg = experiment.config

    down = find_events(experiment.events_log_path, {"event": "churn_is_down"})
    if not down:
        raise ValueError("Churn analysis needs churn_is_down in the events log")

    write_table(
        dump_dir,
        "churn_result",
        churn_table(
            df,
            down[-1]["nodes"],
            cfg.num_messages,
            cfg.num_relay_nodes,
            load_mesh_peers(experiment.output_folder),
        ),
    )
