from typing import Optional

from pydantic import BaseModel


class MetricToScrape(BaseModel):
    name: str
    query: str
    extract_field: str
    folder_name: str
    container: Optional[str] = None
    metrics_path: Optional[str] = None
