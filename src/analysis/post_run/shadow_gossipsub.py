from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.analysis.mesh_analysis.analyzers.data_puller import DataPuller
from src.analysis.mesh_analysis.analyzers.nimlibp2p_analyzer import Nimlibp2pAnalyzer
from src.analysis.metrics.shadow_metrics import scrape_run_metrics

if TYPE_CHECKING:
    from src.deployments.experiments.libp2p.shadow_gossipsub import ShadowGossipsubExperiment

logger = logging.getLogger(__name__)


def run_shadow_gossipsub_analysis(experiment: "ShadowGossipsubExperiment") -> None:
    """Best-effort post-run analysis for Shadow runs."""
    if experiment.output_folder is None:
        logger.error("Shadow post-run analysis requires experiment.output_folder")
        return

    cfg = experiment.config
    run_dir = experiment.output_folder

    try:
        scrape_run_metrics(
            run_dir=run_dir, namespace=experiment.namespace, interval_s=cfg.metrics_interval_s
        )
    except Exception as e:
        logger.error(f"Shadow metrics analysis failed: {e}")
    try:
        puller = DataPuller().with_local(run_dir / "shadow_logs" / "logs")
        (
            Nimlibp2pAnalyzer(dump_analysis_dir=str(run_dir / "analysis_data"))
            .with_data_puller(puller)
            .with_ss_check(["pod"], [cfg.num_nodes])
            .with_reliability_check(
                stateful_sets=["pod"],
                nodes_per_ss=[cfg.num_nodes],
                expected_num_peers=cfg.num_nodes,
                expected_num_messages=cfg.num_messages,
            )
            .run()
        )
    except Exception as e:
        logger.error(f"Shadow message analysis failed: {e}")
