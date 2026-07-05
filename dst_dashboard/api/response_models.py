from typing import Any, Dict, List

from pydantic import BaseModel


class ExperimentSummaryResponse(BaseModel):
    id: str
    title: str
    family: str
    metadata: Dict[str, Any]
    publish: bool


class DatasetResponse(BaseModel):
    experiment_id: str
    dataset_name: str
    row_count: int
    data: List[Dict[str, Any]]


class PanelSummaryResponse(BaseModel):
    id: str
    experiment_id: str
    name: str


class PanelDataResponse(BaseModel):
    experiment_id: str
    panel_name: str
    data: Dict[str, Any]