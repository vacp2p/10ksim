from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


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
    top: Optional[int] = None 


class PanelStyle(BaseModel):
    """Panel style configuration."""
    yLabel: Optional[str] = None
    xLabel: Optional[str] = None
    yUnit: Optional[str] = None
    yMin: Optional[float] = None
    yMax: Optional[float] = None


class PanelConfig(BaseModel):
    name: str
    title: str
    type: Literal["boxplot", "timeseries", "histogram", "bar", "table"]
    dataset: str  # References dataset by name
    transform: PanelTransform
    style: Optional[PanelStyle] = None
    publish: bool  # Whether to show on UI


class ExperimentConfig(BaseModel):
    id: str
    title: str
    family: str
    metadata: Dict[str, Any]  # Flexible metadata from 10ksim
    datasets: List[DatasetConfig]
    panels: List[PanelConfig]
    publish: bool  # Whether to show on UI


class DashboardFullConfig(BaseModel):
    datasources: List[DataSourceConfig]
    experiments: List[ExperimentConfig]
