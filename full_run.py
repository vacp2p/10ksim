"""Entrypoint for end-to-end workflow:

Deploy experiments (or read from a previous deployment's metadata.json)
Analyze
Scrape and plot metrics
"""

import argparse
import asyncio
import logging
import os
import sys
import traceback
from pathlib import Path
from typing import List

from kubernetes import config
from kubernetes.client import ApiClient

from src.analysis.mesh_analysis.analyzers.waku.waku_analyzer import WakuAnalyzer
from src.analysis.mesh_analysis.core import analyze_exps
from src.analysis.metrics.scrapper import Scrapper
from src.analysis.plotting.metrics_plotter import MetricsPlotter
from src.analysis.utils.log_utils import init_logger
from src.deployments.core.k8s_kubeconfig import set_config_file
from src.deployments.experiments.libp2p.nimlibp2p import ExpConfig, NimLibp2pExperiment

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "deployments")))

import asyncio
import logging
import os
import traceback
from pathlib import Path

from kubernetes.client import ApiClient

from src.analysis.metrics.config import ScrapeConfig
from src.analysis.metrics.libp2p.scrape import Nimlibp2pScrapeBuilder
from src.analysis.plotting.config import PlotConfigBuilder
from src.analysis.utils.log_utils import init_logger
from src.deployments.experiments.base_experiment import BaseExperiment

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--config",
        required=False,
        help="Config passed to --kubeconfig in kubernetes commands.",
        default="~/.kube/config",
        dest="kube_config",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        dest="verbosity",
        default=0,
        help="Set the log level: -v (warnings), -vv (info), -vvv (debug) -vvvv (most verbose)",
    )
    parser.add_argument(
        "-l",
        "--out-folder",
        type=Path,
        dest="out_folder",
        default=None,
        required=False,
        help="Output folder to contain all experiment output. "
        "Path is relative to `__file__/out/` unless given as absolute path. "
        "Default path uses `__file__/out/{{datetime}}`.",
    )

    return parser.parse_args()


async def main():
    args = parse_args()

    verbosity = args.verbosity or 2
    init_logger(logging.getLogger(), verbosity)

    logger.debug(f"params: {args}")
    config.load_kube_config(config_file=args.kube_config)
    set_config_file(args.kube_config)
    api_client = ApiClient()

    namespace = "zerotesting-pwhite"
    exps: List[BaseExperiment] = my_experiments(api_client, namespace, args.out_folder)
    for exp in exps:
        try:
            await exp.run()
        except Exception as e:
            logger.error(f"Error running experiment: {e}")
            logger.error(f"exception: {traceback.format_exc()}")

    # paths = []
    # exps = [read_experiment(api_client, path) for path in paths]

    analysis_actions = [lambda: process_experiment(exp) for exp in exps]
    await analyze_exps(analysis_actions)

    scrape_configs = []
    for exp in exps:
        scrape_config = get_scrape_config(exp)
        scrape_configs.append(scrape_config)

    for scrape_config in scrape_configs:
        scrapper = Scrapper(scrape_config)
        scrapper.query_and_dump_metrics()

    plot_configs = get_plots_configs(scrape_configs)
    MetricsPlotter(configs=plot_configs, out_folder=Path("./out/plots")).create_plots()


def my_experiments(api_client: ApiClient, namespace: str, out_folder: str) -> List[BaseExperiment]:
    params_list = [
        ExpConfig(muxer="yamux"),
        ExpConfig(muxer="quic"),
    ]
    return [
        NimLibp2pExperiment(
            api_client=api_client, config=params, namespace=namespace, output_folder=out_folder
        )
        for params in params_list
    ]


async def process_experiment(metadata: dict | BaseExperiment) -> dict:
    if isinstance(metadata, BaseExperiment):
        metadata = metadata.metadata

    exp_name = metadata["stack"]["name"]
    logger.info(f"Processing experiment: {exp_name}\n")

    analyzer = (
        # Nimlibp2pAnalyzer()
        WakuAnalyzer()
        .supports(metadata["experiment"]["name"])
        .with_vaclab()
        .with_metadata(metadata)
        .with_ss_check_from_metadata()
        .with_reliability_from_metadata()
    )

    results_dict = {"metadata": metadata}
    results_dict["results"] = analyzer.run()

    return results_dict


def get_scrape_config(experiment: BaseExperiment) -> ScrapeConfig:
    config: ScrapeConfig = (
        Nimlibp2pScrapeBuilder()
        .with_metadata(experiment.metadata, extract_name=True)
        .with_dump_location(experiment.output_folder / "metrics")
        .with_libp2p_metrics()
        .build()
    )
    return config


def old_data_folders() -> List[Path]:
    # Data from previous reports.
    base = Path(__file__).parent / "nimlibp2pdata"
    return [
        Path(base) / sub
        for sub in [
            "nimlibp2p-1.12.0-1KB",
            "nimlibp2p-1.13.0-1KB",
            "nimlibp2p-1.14.0-1KB",
            "nimlibp2p-1.15.0-1KB",
            "nimlibp2p-1.16.0-1KB",
        ]
    ]


def get_plots_configs(scrape_configs: List[ScrapeConfig]):
    muxers = ["yamux", "quic", "mplex"]
    in_plot = (
        PlotConfigBuilder(name="in")
        .with_metric("libp2p-in")
        .with_folders(old_data_folders())
        .with_include_files(muxers)
        .with_data_from_scrapes(scrape_configs)
        .build()
    )
    out_plot = (
        PlotConfigBuilder(name="out")
        .with_metric("libp2p-out")
        .with_folders(old_data_folders())
        .with_include_files(muxers)
        .with_data_from_scrapes(scrape_configs)
        .build()
    )

    return [in_plot, out_plot]


if __name__ == "__main__":
    asyncio.run(main())
