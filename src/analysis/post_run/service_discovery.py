from __future__ import annotations

from typing import TYPE_CHECKING

from src.analysis.mesh_analysis.analyzers.data_puller import DataPuller
from src.analysis.mesh_analysis.analyzers.service_discovery_analyzer import ServiceDiscoveryAnalyzer

if TYPE_CHECKING:
    from src.deployments.experiments.service_discovery import ServiceDiscovery

VICTORIA_LOGS_URL = "https://vlselect.lab.vac.dev/select/logsql/query"


def run_service_discovery_analysis(experiment: "ServiceDiscovery"):
    if experiment.output_folder is None:
        raise ValueError("Service discovery post-run analysis requires experiment.output_folder")

    stack = dict(experiment.metadata["stack"])
    stack["url"] = VICTORIA_LOGS_URL

    puller = DataPuller().with_kwargs(stack).with_source_type("victoria")

    return (
        ServiceDiscoveryAnalyzer(dump_analysis_dir=experiment.output_folder / "analysis_data")
        .with_data_puller(puller)
        .with_discovery_analysis()
        .run()
    )
