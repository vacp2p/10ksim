import json
import logging
import sys
import traceback
from copy import deepcopy
from pathlib import Path
from typing import Callable, Iterable, List, NamedTuple, Optional, Self, Union

from pydantic import BaseModel, Field

from log_multi_analysis import get_folders
from src.analysis.metrics.libp2p import libp2p_metrics
from src.analysis.metrics.scrapper import Scrapper
from src.analysis.plotting.config import PlotConfigBuilder
from src.analysis.plotting.metrics_plotter import (
    MetricsPlotter,
    MetricToScrape,
    NewScrapeConfig,
    TimeRange,
)

logger = logging.getLogger(__name__)


def setup_logger():
    level = logging.INFO
    logging.getLogger().setLevel(level)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(level)
    logging.getLogger().addHandler(stream_handler)


def number_to_short_str(number: int, capital: bool = False) -> str:
    abs_num = abs(number)
    suffixes = {
        1_000_000_000: "B" if capital else "b",
        1_000_000: "M" if capital else "m",
        1_000: "K" if capital else "k",
    }
    if abs_num >= 1_000_000_000:
        return f"{number // 1_000_000_000}{suffixes[1_000_000_000]}"
    elif abs_num >= 1_000_000:
        return f"{number // 1_000_000}{suffixes[1_000_000]}"
    elif abs_num >= 1_000:
        return f"{number // 1_000}{suffixes[1_000]}"
    else:
        return str(number)


def get_scrape_name(exp: dict) -> str:
    if "NimLibp2pExperiment" in exp["experiment"]["class"]:
        nodes = number_to_short_str(exp["params"]["num_nodes"])
        msg_per = exp["params"]["delay_after_publish"]
        msg_size = number_to_short_str(exp["params"]["message_size_bytes"])
        return f"{nodes}-1mgs-{msg_per}s-{msg_size}bytes"

    raise NotImplementedError()


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
            logger.error(f"exception: {full_trace}")
            raise


class ImageParts(NamedTuple):
    prefix: str  # e.g., "repo/some-certain-thing:maybechars"
    version: str  # e.g., "1.34" or "1.34.0"
    suffix: str  # e.g., "-muxer" or ""


# TODO [scrape builder]: Extract common logic to ScrapeBuidler base class.
class Nimlibp2pScrapeBuilder(BaseModel):
    url: str = "https://metrics.lab.vac.dev/select/0/prometheus/api/v1/"
    rate_interval: Optional[str] = "121s"
    step: str = "60s"
    dump_location: Path = Field(default_factory=lambda: Path("test_results/libp2p"))
    interval: TimeRange = Field(default_factory=TimeRange)
    exp: Optional[dict] = None
    name: Optional[str] = None
    namespace: Optional[str] = None
    metrics_to_scrape: List[MetricToScrape] = Field(default_factory=list)
    has_libp2p_metrics: bool = False

    def with_version(self, version: str) -> Self:
        self.dump_location = self.dump_location / version
        return self

    def with_exp(self, name: str) -> Self:
        self.name = name
        return self

    def with_exp(self, exp: dict, *, extract_name: Optional[bool] = True) -> Self:
        if extract_name:
            self.name = exp["params"]["muxer"]
        self.interval.start = exp["results"]["stable"]["start"]
        self.interval.end = exp["results"]["stable"]["end"]
        self.exp = exp
        if not self.namespace:
            self.namespace = exp["stack"]["namespace"]
        else:
            new_namespace = exp["stack"]["namespace"]
            assert (
                self.namespace == new_namespace
            ), f"Multiple namespace in same scrape config: previous: `{self.namespace}` current: `{new_namespace}`"

        return self

    def with_interval(self, start, end, name) -> Self:
        self.interval.start = start
        self.interval.end = end
        self.name = name
        return self

    def with_libp2p_metrics(self) -> Self:
        # Add later in case self.namespace is not set yet.
        self.has_libp2p_metrics = True
        return self

    def build(self) -> NewScrapeConfig:
        assert self.namespace, "Missing namespace"

        all_metrics = deepcopy(self.metrics_to_scrape)
        if self.has_libp2p_metrics:
            all_metrics.extend(libp2p_metrics(namespace=self.namespace))

        assert self.name, "Missing name"
        return NewScrapeConfig(
            rate_interval=self.rate_interval,
            step=self.step,
            dump_location=self.dump_location,
            metrics_to_scrape=all_metrics,
            name=self.name,
            interval=self.interval,
        )


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


def nimlibp2p_regression_scrape_and_plots():
    folders = [
        Path("/Users/pwhite/vac/repos/10ksim_prs/deployments/out/2026.04.06_11.25.402_7764"),
    ]
    exps = []
    for folder in folders:
        exps.extend(get_nimlibp2p_exps(folder))

    scrapes: NewScrapeConfig = []
    for exp in exps:
        config = Nimlibp2pScrapeBuilder().with_exp(exp, extract_name=True).build()
        scrapes.append(config)
        url = "https://metrics.lab.vac.dev/select/0/prometheus/api/v1/"
        scrapper = Scrapper("~/vac/configs/vaclab.yaml", url, config)
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

    in_plot = (
        PlotConfigBuilder(name="in")
        .with_metric("libp2p-in")
        .with_folders(old_data_folders)
        .with_data_from_scrapes(scrapes)
        .build()
    )
    out_plot = (
        PlotConfigBuilder(name="out")
        .with_metric("libp2p-out")
        .with_folders(old_data_folders)
        .with_data_from_scrapes(scrapes)
        .build()
    )

    MetricsPlotter(configs=[in_plot, out_plot]).create_plots()


def main():
    setup_logger()
    nimlibp2p_regression_scrape_and_plots()


if __name__ == "__main__":
    main()
