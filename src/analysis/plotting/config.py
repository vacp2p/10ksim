from copy import deepcopy
from pathlib import Path
from typing import List, Optional, Self

from pydantic import BaseModel, Field, PositiveInt, model_validator

from src.analysis.data.data_file_handler import DataPath


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

    include_files: Optional[List[str]] = None
    """File names to include inside each metric folder."""


class PlotConfigBuilder(BaseModel):
    name: str
    config: PlotConfig = Field(default=None)

    @model_validator(mode="after")
    def _sync_config(self) -> "PlotConfigBuilder":
        self.config = PlotConfig(name=self.name)
        return self

    def with_metric(self, metric: str) -> Self:
        self.config.metrics.append(metric.strip("/"))
        return self

    def with_group(self, name: str, data_paths: List[DataPath] | DataPath) -> Self:
        """Each group corresponds to an entry in the plot legend.
        Each DataPath entry corresponds to a point along the x-axis"""
        if isinstance(data_paths, DataPath):
            data_paths = [data_paths]
        self.config.groups.append(DataGroup(name=name, data_paths=data_paths))
        return self

    def with_groups(self, groups: List[DataGroup] | DataGroup) -> Self:
        if isinstance(groups, DataGroup):
            groups = [groups]
        self.config.groups.extend(groups)
        return self

    def with_folders(
        self, folders: List[str | Path] | str | Path, *, group_name: str = "folders"
    ) -> Self:
        if isinstance(folders, str) or isinstance(folders, Path):
            folders = [folders]

        data_paths = [DataPath(name=Path(folder).name, path=Path(folder)) for folder in folders]
        if data_paths:
            self.config.groups.append(DataGroup(name=group_name, data_paths=data_paths))

        return self

    def with_include_files(self, include_files: List[str] | str) -> Self:
        if isinstance(include_files, str):
            include_files = [include_files]
        self.config.include_files = include_files
        return self

    def with_x_order(self, x_order: List[str] | str) -> Self:
        if isinstance(x_order, str):
            x_order = [x_order]
        self.config.x_order = x_order
        return self

    def with_legend_order(self, legend_order: List[str] | str) -> Self:
        if isinstance(legend_order, str):
            legend_order = [legend_order]
        self.config.legend_order = legend_order
        return self

    def build(self) -> PlotConfig:
        return deepcopy(self.config)
