import argparse
import logging
import os
from pathlib import Path
from typing import Iterable, Union

from src.analysis.metrics.config import ScrapeConfig
from src.analysis.metrics.libp2p.scrape import Nimlibp2pScrapeBuilder
from src.analysis.metrics.scrapper import Scrapper
from src.analysis.plotting.config import PlotConfigBuilder
from src.analysis.plotting.metrics_plotter import MetricsPlotter
from src.analysis.utils.file_utils import extract_exps, get_folders
from src.analysis.utils.log_utils import init_logger

logger = logging.getLogger(__name__)


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
            .with_metadata(exp, extract_name=True)
            .with_dump_location(dump_fmt.format(i=i))
            .with_libp2p_metrics()
            .build()
        )
        scrapes.append(config)
        scrapper = Scrapper(config, k8s_config)
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

    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        dest="verbosity",
        default=0,
        help="Set the log level: -v (warnings), -vv (info), -vvv (debug) -vvvv (most verbose)",
    )

    return parser.parse_args()


def main():
    args = parse_args()
    verbosity = args.verbosity or 2
    init_logger(logging.getLogger(), verbosity, None)
    params = parse_args()
    nimlibp2p_regression_scrape_and_plots(params.config)


if __name__ == "__main__":
    main()
