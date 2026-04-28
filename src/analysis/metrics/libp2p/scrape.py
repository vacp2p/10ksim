from copy import deepcopy
from pathlib import Path
from typing import List, Optional, Self

from pydantic import BaseModel, Field

from src.analysis.metrics.config import MetricToScrape, ScrapeConfig
from src.analysis.metrics.libp2p.metrics import libp2p_metrics
from src.analysis.utils.time_utils import TimeRange


# TODO [scrape builder]: Extract common logic to ScrapeBuilder base class.
class Nimlibp2pScrapeBuilder(BaseModel):
    rate_interval: Optional[str] = "121s"
    step: str = "60s"
    dump_location: Path = Field(default_factory=lambda: Path("test_results/libp2p"))
    interval: TimeRange = Field(default_factory=TimeRange)
    exp: Optional[dict] = None
    name: Optional[str] = None
    namespace: Optional[str] = None
    metrics_to_scrape: List[MetricToScrape] = Field(default_factory=list)
    has_libp2p_metrics: bool = False

    def with_dump_location(self, folder: str) -> Self:
        self.dump_location = folder
        return self

    def with_metadata(self, metadata: dict, *, extract_name: Optional[bool] = True) -> Self:
        if extract_name:
            self.name = metadata["experiment"]["dump"]["config"]["muxer"]
        self.interval.start = metadata["results"]["stable"]["start"]
        self.interval.end = metadata["results"]["stable"]["end"]
        self.exp = metadata
        if not self.namespace:
            self.namespace = metadata["stack"]["namespace"]
        else:
            new_namespace = metadata["stack"]["namespace"]
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
        # Add metrics later, in case self.namespace is not set yet.
        self.has_libp2p_metrics = True
        return self

    def build(self) -> ScrapeConfig:
        assert self.namespace, "Missing namespace"

        all_metrics = deepcopy(self.metrics_to_scrape)
        if self.has_libp2p_metrics:
            all_metrics.extend(libp2p_metrics(namespace=self.namespace))

        assert self.name, "Missing name"
        return ScrapeConfig(
            rate_interval=self.rate_interval,
            step=self.step,
            dump_location=self.dump_location,
            metrics_to_scrape=all_metrics,
            name=self.name,
            interval=self.interval,
        )
