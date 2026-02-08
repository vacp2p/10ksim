import argparse
import json
import logging
import os
import sys
import traceback
from pathlib import Path
from typing import Callable, Iterable, List, Union

from log_multi_analysis import get_folders
from src.analysis.metrics.config import ScrapeConfig
from src.analysis.metrics.libp2p.scrape import Nimlibp2pScrapeBuilder
from src.analysis.metrics.scrapper import Scrapper
from src.analysis.plotting.config import PlotConfigBuilder
from src.analysis.plotting.metrics_plotter import MetricsPlotter

logger = logging.getLogger(__name__)


def setup_logger():
    level = logging.INFO
    logging.getLogger().setLevel(level)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(level)
    logging.getLogger().addHandler(stream_handler)


def extract_exps(folders: List, filters: List[Callable[[dict], bool]]) -> Iterable[dict]:
    for folder in folders:
        try:
            metadata_log_path = Path(folder) / "metadata.json"
            logger.info(f"Events log path: {metadata_log_path}")
            with open(metadata_log_path, "r", encoding="utf-8") as f:
                exp = json.load(f)
            if any(filter(exp) == False for filter in filters):
                logger.warning(
                    f"Experiment filtered out. path: `{metadata_log_path}` metadata: `{exp}`"
                )
                continue
            yield exp
        except Exception as e:
            full_trace = traceback.format_exc()
            logger.error(f"exception: {e}\n{full_trace}")
            raise


def get_nimlibp2p_exps(folder: Union[str, Path]) -> Iterable[dict]:
    experiment_class = "NimLibp2pExperiment"

    def filter_by_class(exp) -> bool:
        if exp["experiment"]["class"] != experiment_class:
            return False
        return True

    filters = []
    if experiment_class:
        filters.append(filter_by_class)

    paths = [folder / path for path in get_folders(Path(folder), "metadata.json")]
    for d in paths:
        logger.info(d)
        for exp in extract_exps(paths, filters):
            yield exp


def nimlibp2p_regression_scrape_and_plots(k8s_config: str):
    folders = [
        # TODO: Put paths here.
    ]
    exps = []
    for folder in folders:
        exps.extend(get_nimlibp2p_exps(folder))

    scrapes: ScrapeConfig = []
    dump_fmt = "test_results/libp2p/1.16.0"
    if len(exps) > 1:
        dump_fmt += "_run_{i}"
    for i, exp in enumerate(exps):
        config = (
            Nimlibp2pScrapeBuilder()
            .with_exp(exp, extract_name=True)
            .with_dump_location(dump_fmt.format(i=i))
            .with_libp2p_metrics()
            .build()
        )
        scrapes.append(config)
        scrapper = Scrapper(k8s_config, config)
        scrapper.query_and_dump_metrics()

    # Data from previous reports.
    base = Path(__file__).parent / "nimlibp2pdata"
    old_data_folders = [
        Path(base) / sub
        for sub in [
            "nimlibp2p-1.12.0-1KB",
            "nimlibp2p-1.13.0-1KB",
            "nimlibp2p-1.14.0-1KB",
            "nimlibp2p-1.15.0-1KB",
            "nimlibp2p-1.16.0-1KB",
        ]
    ]

    muxers = ["yamux", "quic", "mplex"]
    in_plot = (
        PlotConfigBuilder(name="in")
        .with_metric("libp2p-in")
        .with_folders(old_data_folders)
        .with_include_files(muxers)
        .with_data_from_scrapes(scrapes)
        .build()
    )
    out_plot = (
        PlotConfigBuilder(name="out")
        .with_metric("libp2p-out")
        .with_folders(old_data_folders)
        .with_include_files(muxers)
        .with_data_from_scrapes(scrapes)
        .build()
    )

    MetricsPlotter(configs=[in_plot, out_plot]).create_plots()


def default_kubeconfig_path() -> str:
    return os.environ.get("KUBECONFIG", str(Path.home() / ".kube" / "config"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default=default_kubeconfig_path(),
        help="Path to kubeconfig file",
    )
    return parser.parse_args()


def main():
    setup_logger()
    params = parse_args()
    nimlibp2p_regression_scrape_and_plots(params.config)


if __name__ == "__main__":
    main()
