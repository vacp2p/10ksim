import logging
from copy import deepcopy
from pathlib import Path
from typing import List, Optional, Self

from pydantic import BaseModel, Field

from src.analysis.metrics.config import MetricToScrape, ScrapeConfig
from src.analysis.metrics.libp2p.metrics import gossipsub_detail_metrics, libp2p_metrics
from src.analysis.utils.time_utils import TimeRange

logger = logging.getLogger(__name__)


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
    has_gossipsub_detail: bool = False

    @staticmethod
    def _parse_interval(interval: Optional[dict]) -> Optional[TimeRange]:
        if not interval or "start" not in interval or "end" not in interval:
            return None

        try:
            parsed = TimeRange()
            parsed.start = interval["start"]
            parsed.end = interval["end"]
        except (TypeError, ValueError):
            return None

        return parsed if parsed.start is not None and parsed.end is not None else None

    @classmethod
    def _select_interval(cls, exp: dict) -> TimeRange:
        results = exp["results"]
        stable = results.get("stable")
        stable_interval = cls._parse_interval(stable)
        if stable_interval:
            return stable_interval

        complete = results.get("complete")
        complete_interval = cls._parse_interval(complete)
        if complete_interval:
            logger.warning(
                "Ignoring invalid stable interval and using complete interval instead: %s",
                stable,
            )
            return complete_interval

        raise ValueError(
            "Experiment does not contain a valid stable or complete interval: "
            f"stable={stable!r}, complete={complete!r}"
        )

    def with_dump_location(self, folder: str) -> Self:
        self.dump_location = folder
        return self

    def with_exp(self, exp: dict, *, extract_name: Optional[bool] = True) -> Self:
        if extract_name:
            self.name = exp["params"]["muxer"]
        interval = self._select_interval(exp)
        self.interval.start = interval.start
        self.interval.end = interval.end
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
        # Add metrics later, in case self.namespace is not set yet.
        self.has_libp2p_metrics = True
        return self

    def with_gossipsub_detail_metrics(self) -> Self:
        # Gossipsub control-traffic + efficiency counters (IHAVE/IWANT/GRAFT/PRUNE,
        # duplicates, IDONTWANT). Deferred like with_libp2p_metrics so namespace can be set.
        self.has_gossipsub_detail = True
        return self

    def build(self) -> ScrapeConfig:
        assert self.namespace, "Missing namespace"

        all_metrics = deepcopy(self.metrics_to_scrape)
        if self.has_libp2p_metrics:
            all_metrics.extend(libp2p_metrics(namespace=self.namespace))
        if self.has_gossipsub_detail:
            all_metrics.extend(gossipsub_detail_metrics(namespace=self.namespace))

        assert self.name, "Missing name"
        return ScrapeConfig(
            rate_interval=self.rate_interval,
            step=self.step,
            dump_location=self.dump_location,
            metrics_to_scrape=all_metrics,
            name=self.name,
            interval=self.interval,
            exp=self.exp,
        )
