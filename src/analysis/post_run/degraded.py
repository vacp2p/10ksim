"""Post-run analysis for the degraded-network scenario."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List, Optional

import pandas as pd

from src.analysis.post_run.scenario_common import (
    Row,
    latency_summary,
    load_mesh_peers,
    mesh_peers_row,
    pct,
    prepare,
    published_messages,
    write_table,
)

if TYPE_CHECKING:
    from src.deployments.experiments.libp2p.nimlibp2p import NimLibp2pExperiment

logger = logging.getLogger(__name__)


def degraded_table(
    df: pd.DataFrame,
    num_messages: int,
    num_nodes: int,
    mesh: Optional[pd.DataFrame] = None,
) -> List[Row]:
    """Delivery should be complete and latency should track the injected delay."""
    return [
        ("delivery", "100%", pct(len(df), num_messages * num_nodes)),
        ("median latency", "roughly mesh depth x the injected delay", latency_summary(df)),
        ("latency tail", "bounded, no collapse", f"max {df['delayMs'].max():.0f} ms"),
        mesh_peers_row(mesh, "mesh peers per node"),
    ]


def run_degraded_analysis(experiment: "NimLibp2pExperiment") -> None:
    dump_dir, df = prepare(experiment)
    cfg = experiment.config
    write_table(
        dump_dir,
        "degraded_result",
        degraded_table(
            df,
            published_messages(experiment),
            cfg.num_relay_nodes,
            load_mesh_peers(experiment.output_folder),
        ),
    )
