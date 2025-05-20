# Python Imports
from abc import ABC, abstractmethod
from typing import List, Any


class MonitoringClient(ABC):

    def __init__(self):
        pass

    @abstractmethod
    def query_logs(self, pod_name: str, container_name: str, start_time: str, end_time: str,
                   expressions: List[str]) -> Any:
        raise NotImplementedError
