# Python Imports
from typing import List, Dict

# Project Imports
from src.mesh_analysis.monitoring_clients.monitoring_client import MonitoringClient


class VictoriaMetricsClient(MonitoringClient):

    def __init__(self, url: str):
        super().__init__()
        self._url = url  # https://vmselect.riff.cc/select/logsql/query

    def query_logs(self, pod_name: str, container_name: str, start_time: str, end_time: str,
                   expressions: List[str]) -> Dict:
        query = {'url': f'{self._url}',
                 'headers': {'Content-Type': 'application/json'},
                 'params': []
                 }

        for expression in expressions:
            query['params'].append({'query': f'kubernetes.container_name:{container_name} AND kubernetes.pod_name:{pod_name} AND {expression} AND _time:[{start_time}, {end_time}]'})  # [2025-03-12T11:40:00, 2025-03-12T12:27:00]

        return query
