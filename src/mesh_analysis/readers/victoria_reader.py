# Python Imports
import json
import logging
import re
import time
import requests
from typing import Dict, List, Optional, Iterator
from httpx import Response
from result import Result, Ok, Err

# Project Imports
from src.mesh_analysis.tracers.message_tracer import MessageTracer

logger = logging.getLogger(__name__)


class VictoriaReader:

    def __init__(self, config: Dict, tracer: Optional[MessageTracer]):
        self._config = config
        self._tracer = tracer
        self.logs = []

    def _fetch_data(self, headers: Dict, params: Dict):
        logger.info(f'Fetching {params}')
        # time.sleep(5)
        with requests.post(self._config['url'], headers=headers, params=params, stream=True) as response:
            for line in response.iter_lines():
                if line:
                    try:
                        parsed_object = json.loads(line)
                    except json.decoder.JSONDecodeError as e:
                        logger.info(line)
                        exit()
                    self.logs.append((parsed_object['_msg'], parsed_object['kubernetes_pod_name']))
                    logger.debug("line added")
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
            logger.info('Fetched lines parsed with pattern')
            self.logs.clear()

        return results

    def read(self) -> List:
        logger.info(f'Reading {self._config["url"]}')

        results = self._make_queries()
        dfs = self._tracer.trace(results)

        return dfs

    def single_query_info(self) -> Result[Dict, Response]:
        time.sleep(10)
        response = requests.post(self._config['url'], headers=self._config['headers'], params=self._config['params'])
        if response.status_code != 200:
            logger.error(f'Request failed with status code: {response.status_code}')
            return Err(response)

        try:
            data = response.json()
            return Ok(data)
        except json.decoder.JSONDecodeError as e:
            logger.error(f'Failed to decode JSON: {e}')
            logger.error(f'Response content: {response.content}')

    def multi_query_info(self) -> Result[Iterator, Response]:
        time.sleep(10)
        response = requests.post(self._config['url'], headers=self._config['headers'], params=self._config['params'])
        if response.status_code != 200:
            logger.error(f'Request failed with status code: {response.status_code}')
            return Err(response)

        try:
            data = response.iter_lines()
            return Ok(data)
        except json.decoder.JSONDecodeError as e:
            logger.error(f'Failed to decode JSON: {e}')
            logger.error(f'Response content: {response.content}')