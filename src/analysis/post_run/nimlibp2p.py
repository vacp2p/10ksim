from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.analysis.mesh_analysis.analyzers.data_puller import DataPuller
from src.analysis.mesh_analysis.analyzers.nimlibp2p_analyzer import Nimlibp2pAnalyzer
from src.analysis.plotting.latency_plotter import plot_dump_latency
from src.analysis.post_run.metrics import plot_run_metrics, scrape_run_metrics

if TYPE_CHECKING:
    from src.deployments.experiments.libp2p.nimlibp2p import NimLibp2pExperiment

logger = logging.getLogger(__name__)

VICTORIA_LOGS_URL = "https://vlselect.lab.vac.dev/select/logsql/query"
REQUIRED_TIME_WINDOW_KEYS = ("start_time", "end_time")


def _require_bounded_query(stack: dict) -> None:
    missing = [key for key in REQUIRED_TIME_WINDOW_KEYS if not stack.get(key)]
    if missing:
        raise ValueError(
            "Nimlibp2p post-run analysis requires a bounded metadata stack; "
            f"missing: {missing}. Refusing to run an unbounded VictoriaLogs query."
        )


def run_nimlibp2p_analysis(experiment: "NimLibp2pExperiment") -> None:
    """Message reliability and delivery latency for a finished cluster run."""
    if experiment.output_folder is None:
        raise ValueError("Nimlibp2p post-run analysis requires experiment.output_folder")
    if experiment.metadata is None:
        raise ValueError("Nimlibp2p post-run analysis requires experiment.metadata")

    cfg = experiment.config
    stack = dict(experiment.metadata["stack"])
    stack.update(
        {
            "type": "vaclab",
            "url": VICTORIA_LOGS_URL,
            "reader": "victoria",
            "namespace": experiment.namespace or stack.get("namespace"),
        }
    )
    _require_bounded_query(stack)

    # Bootstrap nodes do not relay, so they are excluded from the delivery counts.
    relays = [
        pair
        for pair in zip(stack["stateful_sets"], stack["nodes_per_statefulset"])
        if "bootstrap" not in pair[0]
    ]
    dump_dir = experiment.output_folder / "analysis_data"

    try:
        (
            Nimlibp2pAnalyzer(dump_analysis_dir=str(dump_dir))
            .with_data_puller(DataPuller().with_kwargs(stack))
            .with_ss_check(stack["stateful_sets"], stack["nodes_per_statefulset"])
            .with_reliability_check(
                stateful_sets=[name for name, _ in relays],
                nodes_per_ss=[count for _, count in relays],
                expected_num_peers=cfg.num_relay_nodes,
                expected_num_messages=cfg.num_messages,
            )
            .run()
        )
    except Exception:
        logger.exception("Nimlibp2p message analysis failed")
    try:
        plot_dump_latency(dump_dir, label=cfg.muxer)
    except Exception:
        logger.exception("Nimlibp2p latency plot failed")
    try:
        _scrape_and_plot(experiment)
    except Exception:
        logger.exception("Nimlibp2p metrics scrape failed")


def _scrape_and_plot(experiment: "NimLibp2pExperiment") -> None:
    """Resource and mesh-health figures, off the run's own stable window."""
    exp = experiment.metadata
    if not exp.get("results", {}).get("stable"):
        logger.warning("Run has no stable window; skipping the metrics scrape")
        return

    label = experiment.config.muxer
    dump = scrape_run_metrics(exp, experiment.output_folder / "metrics", name=label)
    plot_run_metrics(
        {label: dump},
        experiment.output_folder / "plots",
        xlabel=f"{experiment.namespace}, {experiment.config.num_relay_nodes} nodes",
    )
