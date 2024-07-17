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
                    self.logs.append(parsed_object['_msg'])
        logger.info(f'Fetched {len(self.logs)} messages')

    def read(self) -> List:
        logger.info(f'Reading {self._config["url"]}')

        self._fetch_data(self._config["headers"], self._config["params"])

        results = [[] for _ in self._tracer.patterns]
        for log_line in self.logs:
            for i, pattern in enumerate(self._tracer.patterns):
                match = re.search(pattern, log_line)
                if match:
                    results[i].append(match.groups())

        dfs = self._tracer.trace(results)

        return dfs
