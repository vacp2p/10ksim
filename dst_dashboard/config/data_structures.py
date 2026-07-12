from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel


class TimeRange(BaseModel):
    """Time range for data queries."""

    start: datetime
    end: datetime


class DataSourceConfig(BaseModel):
    """Global datasource configuration."""

    name: str
    type: Literal["VictoriaLogs", "Prometheus"]
    url: str


class DatasetQuery(BaseModel):
    """Query configuration for a dataset."""

    namespace: Optional[str] = None
    tracer: Optional[str] = None  # For logs: nimlibp2p, kad_dht, waku
    pattern: Optional[str] = None  # For logs: received, lookup, etc.
    expr: Optional[str] = None  # For metrics: PromQL expression
    step: Optional[str] = None  # For metrics: step interval


class SchemaField(BaseModel):
    """Schema field definition."""

    name: str
    type: Literal["datetime", "string", "float", "integer", "boolean"]


class DatasetConfig(BaseModel):
    """Dataset configuration - raw data from datasources."""

    name: str
    datasource: str  # References global datasource by name
    timeRange: TimeRange
    query: DatasetQuery
    schema: List[SchemaField]


class DeriveField(BaseModel):
    """Derived field transformation in panel."""

    name: str
    function: str  # regex_match, aggregate, etc.
    field: str  # Source field
    pattern: Optional[str] = None  # For regex
    match: Optional[str] = None  # Regex match value
    no_match: Optional[str] = None  # Regex no-match value


class PanelTransform(BaseModel):
    """Panel transformation configuration."""

    derive: Optional[List[DeriveField]] = None
    groupBy: Optional[str] = None
    value: Optional[str] = None
    x: Optional[str] = None
    y: Optional[str] = None
    top: Optional[int] = None  # Top N by average value
    firstN: Optional[int] = None  # First N items (no sorting)


class PanelStyle(BaseModel):
    """Panel style configuration."""

    yLabel: Optional[str] = None
    xLabel: Optional[str] = None
    yUnit: Optional[Literal["bytes", "bytes/s", "bps", "ms", "seconds", "percent", "number"]] = (
        None  # Auto-format units
    )
    yMin: Optional[float] = None
    yMax: Optional[float] = None


class PanelConfig(BaseModel):
    name: str
    title: str
    type: Literal["boxplot", "timeseries", "histogram", "bar", "table"]
    dataset: str  # References dataset by name
    transform: PanelTransform
    style: Optional[PanelStyle] = None
    echarts_options: Optional[Dict[str, Any]] = (
        None  # Override ECharts options (colors, grid, etc.)
    )
    publish: bool  # Whether to show on UI


class ExperimentConfig(BaseModel):
    id: Optional[str] = None  # Server-assigned on create; ignored if sent by the client
    title: str
    family: str
    description: Optional[str] = None  # Experiment description
    metadata: Dict[str, Any]  # Flexible metadata from 10ksim
    datasets: List[DatasetConfig]
    panels: List[PanelConfig]
    publish: bool  # Whether to show on UI
    github_repo: Optional[str] = None  # GitHub repository URL
    github_pr: Optional[str] = None  # Pull request URL
    docker_image: Optional[str] = None  # Docker image reference
    date: Optional[str] = None  # ISO date string (YYYY-MM-DD)


class DashboardFullConfig(BaseModel):
    datasources: List[DataSourceConfig]

    def WithValidateDatasources(self) -> "DashboardFullConfig":
        if not self.datasources:
            raise ValueError("At least one datasource must be defined in the config.")
        for datasource in self.datasources:
            if not datasource.name:
                raise ValueError("Datasource must have a name.")
            if not datasource.type:
                raise ValueError("Datasource must have a type.")
            if not datasource.url:
                raise ValueError("Datasource must have a URL.")
        return self
