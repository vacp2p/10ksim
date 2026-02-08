from copy import deepcopy
from typing import List, Optional, Self

from pydantic import BaseModel, Field, PositiveInt, model_validator

from analysis.config import NewScrapeConfig
from src.metrics.config import MetricToScrape


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

    # TODO [plotter config]: Change to paths. Edit plotter too.
    folder: List[str] = Field(default_factory=list)
    data: List[str] = Field(default_factory=list)
    include_files: List[str] = Field(default_factory=list)


class PlotConfigBuilder(BaseModel):
    name: str
    config: PlotConfig = Field(default=None)

    @model_validator(mode="after")
    def _sync_config(self) -> "PlotConfigBuilder":
        self.config = PlotConfig(name=self.name)
        return self

    def with_metric(self, metric: MetricToScrape | str) -> Self:
        if isinstance(metric, MetricToScrape):
            self.config.data.append(metric.folder_name.strip("/"))
        else:
            self.config.data.append(metric.strip("/"))
        return self

    def with_include_files(self, includes: List[str] | str) -> Self:
        self.config.include_files.extend(includes)
        return self

    def with_folders(self, folders: List[str] | str) -> Self:
        # TODO [plotter config]: This hack will be removed.
        def ensure_trailing_slash(folder: str) -> str:
            if folder.endswith("/"):
                return folder
            else:
                return f"{folder}/"

        folders = [ensure_trailing_slash(folder) for folder in folders]
        self.config.folder.extend(folders)
        return self

    def with_scrape_metrics(self, scrape_config: NewScrapeConfig) -> Self:
        for metric in scrape_config.metrics_to_scrape:
            self.with_metric(metric)
        return self

    def with_data_from_scrapes(
        self, scrape_configs: List[NewScrapeConfig] | NewScrapeConfig
    ) -> Self:
        if isinstance(scrape_configs, NewScrapeConfig):
            scrape_configs = [scrape_configs]
        self.config.include_files.extend([config.name for config in scrape_configs])
        self.config.folder.extend([config.dump_location for config in scrape_configs])
        return self

    def build(self) -> PlotConfig:
        return deepcopy(self.config)
