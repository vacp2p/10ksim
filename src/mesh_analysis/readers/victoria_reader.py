# Python Imports
import json
import logging
import re
import requests
from typing import Dict, List

# Project Imports
from src.mesh_analysis.tracers.message_tracer import MessageTracer

logger = logging.getLogger(__name__)


class VictoriaReader:

    def __init__(self, config: Dict, tracer: MessageTracer):
        self._config = config
        self._tracer = tracer
        self.logs = []

    def _fetch_data(self, headers: Dict, params: Dict):
        with requests.post(self._config['url'], headers=headers, params=params, stream=True) as response:
            for line in response.iter_lines():
                if line:
                    parsed_object = json.loads(line)
                    self.logs.append((parsed_object['_msg'], parsed_object['kubernetes_pod_name']))
        logger.info(f'Fetched {len(self.logs)} messages')

    def _make_queries(self) -> List:
        results = [[] for _ in self._tracer.patterns]

        for i, query in enumerate(self._config['params']):
            self._fetch_data(self._config["headers"], query)
            for log_line in self.logs:
                match = re.search(self._tracer.patterns[i], log_line[0])
                if match:
                    match_as_list = list(match.groups())
                    match_as_list.append(log_line[1])
                    results[i].append(match_as_list)
            self.logs.clear()

        return results

    def read(self) -> List:
        logger.info(f'Reading {self._config["url"]}')

        results = self._make_queries()
        dfs = self._tracer.trace(results)

        return dfs
