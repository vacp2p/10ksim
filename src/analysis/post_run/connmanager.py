from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.analysis.connmanager_analysis import (
    plot_connection_count,
    plot_direction_breakdown,
    plot_trim_timeline,
)
from src.analysis.mesh_analysis.analyzers.connmanager_analyzer import ConnManagerAnalyzer
from src.analysis.mesh_analysis.analyzers.data_puller import DataPuller

if TYPE_CHECKING:
    from src.deployments.experiments.libp2p.connmanager import ConnManagerExperiment

logger = logging.getLogger(__name__)

VICTORIA_LOGS_URL = "https://vlselect.lab.vac.dev/select/logsql/query"
REQUIRED_TIME_WINDOW_KEYS = ("start_time", "end_time")


def _require_bounded_query(stack: dict) -> None:
    missing = [key for key in REQUIRED_TIME_WINDOW_KEYS if not stack.get(key)]
    if missing:
        raise ValueError(
            "Connmanager post-run analysis requires a bounded metadata stack; "
            f"missing: {missing}. Refusing to run an unbounded VictoriaLogs query."
        )


def run_connmanager_analysis(experiment: "ConnManagerExperiment") -> None:
    logger.info("Running connmanager post-run analysis")

    if experiment.output_folder is None:
        raise ValueError("Connmanager post-run analysis requires experiment.output_folder")
    if experiment.metadata is None:
        raise ValueError("Connmanager post-run analysis requires experiment.metadata")

    stack = dict(experiment.metadata["stack"])
    stack.update(
        {
            "type": "vaclab",
            "url": VICTORIA_LOGS_URL,
            "reader": "victoria",
            "stateful_sets": ["hub"],
            "nodes_per_statefulset": [1],
            "container_name": "pod-0",
            "namespace": experiment.namespace or stack.get("namespace"),
            "extra_fields": ["kubernetes.pod_name"],
        }
    )

    puller = DataPuller().with_kwargs(stack)
    wave_sets = ["wave1", "wave2"] if experiment.config.run.upper() == "B" else None
    workdir = experiment.output_folder / "deployment_yamls"

    analyzer = (
        ConnManagerAnalyzer(dump_analysis_dir=workdir / "analysis_data")
        .with_data_puller(puller)
        .with_hub_analysis(
            hub_pod="hub-0",
            grace_period_s=experiment.config.grace_period_s,
            protected_peer_ids=experiment.config.protected_peer_ids or None,
            wave_sets=wave_sets,
        )
    )

    results = analyzer.run()

    out_dir = workdir / "plots"
    out_dir.mkdir(parents=True, exist_ok=True)

    for result in results:
        if result.name == "connmanager" and result.intermediates:
            conn_df = result.intermediates.get("conn_df")
            drop_df = result.intermediates.get("drop_df")
            if conn_df is not None and not conn_df.empty:
                plot_connection_count(conn_df, drop_df, str(out_dir))
                plot_direction_breakdown(conn_df, result.intermediates, str(out_dir))
                plot_trim_timeline(conn_df, drop_df, str(out_dir))

    logger.info(f"Connmanager post-run analysis complete. Plots saved to {out_dir}")
