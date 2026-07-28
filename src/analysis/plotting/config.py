from copy import deepcopy
from pathlib import Path
from typing import List, Optional, Self

from pydantic import BaseModel, Field, PositiveInt, model_validator

from src.analysis.data.data_file_handler import DataPath
from src.analysis.metrics.config import MetricToScrape, ScrapeConfig
from src.deployments.utils.flatten import flatten


class DataGroup(BaseModel):
    name: str
    """Group name"""
    data_paths: List[DataPath]


class PlotConfig(BaseModel):
    name: Optional[str] = None
    ignore_columns: List[str] = Field(default_factory=lambda: ["bootstrap", "midstrap"])
    data_points: PositiveInt = Field(default=25)
    xlabel_name: str = "Simulation"
    ylabel_name: str = "KBytes/s"
    show_min_max: bool = False
    outliers: bool = True
    scale_x: PositiveInt = 1000
    fig_size: List[PositiveInt] = Field(default_factory=lambda: [20, 20])

    x_order: Optional[List[str]] = None
    legend_order: Optional[List[str]] = None

    groups: List[DataGroup] = Field(default_factory=list)
    """Each group will appear as a separate item in the legend."""

    metrics: List[str] = Field(default_factory=list)
    """List of metrics to include in plots."""


class PlotConfigBuilder(BaseModel):
    name: str
    config: PlotConfig = Field(default=None)

    @model_validator(mode="after")
    def _sync_config(self) -> "PlotConfigBuilder":
        self.config = PlotConfig(name=self.name)
        return self

    def with_metric(self, metric: MetricToScrape | str) -> Self:
        if isinstance(metric, MetricToScrape):
            self.config.metrics.append(metric.name.strip("/"))
        else:
            self.config.metrics.append(metric.strip("/"))
        return self

    def with_group(self, name: str, inputs: list) -> Self:
        """Each group corresponds to an entry in the plot legend.
        Each DataPath entry corresponds to a point along the x-axis"""
        data_paths = []
        for item in flatten(inputs):
            if isinstance(item, ScrapeConfig):
                path_name = item.dump_location.parent.name
                data_paths.append(DataPath(name=path_name, path=item.dump_location))
            elif isinstance(item, DataPath):
                data_paths.append(item)
        self.config.groups.append(DataGroup(name=name, data_paths=data_paths))
        return self

    def with_folders(self, folders: List[str | Path] | str | Path) -> Self:
        if isinstance(folders, str) or isinstance(folders, Path):
            folders = [folders]

        # TODO [plotter config]: This hack will be removed.
        def ensure_trailing_slash(folder: str | Path) -> str:
            if isinstance(folder, Path):
                folder = folder.as_posix()
            if folder.endswith("/"):
                return folder
            else:
                return f"{folder}/"

        folders = [ensure_trailing_slash(folder) for folder in folders]
        self.config.folder.extend(folders)
        return self

    def with_scrape_metrics(self, scrape_config: ScrapeConfig) -> Self:
        for metric in scrape_config.metrics_to_scrape:
            self.with_metric(metric)
        return self

    def with_data_from_scrapes(self, scrape_configs: List[ScrapeConfig] | ScrapeConfig) -> Self:
        if isinstance(scrape_configs, ScrapeConfig):
            scrape_configs = [scrape_configs]
        self.with_folders([config.dump_location for config in scrape_configs])
        return self

    def build(self) -> PlotConfig:
        return deepcopy(self.config)
