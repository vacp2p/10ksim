from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

import yaml
from pydantic import BaseModel, Field

from src.metrics.config import MetricToScrape
from src.plotting.metrics_plotter import TimeRange


class NewScrapeConfig(BaseModel):
    """The window of the time that you are looking."""

    rate_interval: Optional[str] = "121s"
    step: str = "60s"
    dump_location: Path = Field(default_factory=lambda: Path("test_results/"))
    metrics_to_scrape: List[MetricToScrape] = Field(default_factory=list)
    name: str
    interval: TimeRange
    exp: Optional[dict] = None

    @property
    def start(self) -> Optional[datetime]:
        return self.interval.start

    @start.setter
    def start(self, value: Any) -> None:
        self.interval.start = value

    @property
    def end(self) -> Optional[datetime]:
        return self.interval.end

    @end.setter
    def end(self, value: Any) -> None:
        self.interval.end = value

    def scrape_line(self) -> str:
        if self.exp:
            params_list = [f"{key}_{value}" for key, value in self.exp["params"].items()]
            params = "  ".join(params_list)
        else:
            params = ""
        return f'- ["{self.interval.start}", "{self.interval.end}", "{self.name}"] # {params}'

    def dump_str(self, dump_path: str):
        config_dict = {
            "scrape_config": {
                "$__rate_interval": self.rate_interval,
                "step": self.step,
                "dump_location": self.dump_location,
            },
            "metrics_to_scrape": [metric.model_dump() for metric in self.metrics_to_scrape],
        }
        other_yaml = yaml.dump(config_dict, default_flow_style=False, sort_keys=False, indent=4)
        times_lines = ["general_config:", "  times_names:" f"    {self.scrape_line()}"]
        times_block = "\n".join(times_lines)
        result = times_block + "\n\n" + other_yaml + "\n"
        return result
