# Python Imports
import json
import logging
import re
import pandas as pd
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
        logger.debug(f'Fetching {params}')
        # time.sleep(5)
        with requests.post(self._config['url'], headers=headers, params=params, stream=True) as response:
            for line in response.iter_lines():
                if line:
                    try:
                        parsed_object = json.loads(line)
                    except json.decoder.JSONDecodeError as e:
                        logger.info(line)
                        exit()
                    self.logs.append((parsed_object['_msg'], parsed_object['kubernetes.pod_name'], parsed_object['kubernetes.pod_node_name']))
        logger.debug(f'Fetched {len(self.logs)} messages')

    def _make_queries(self) -> List:
        results = [[] for _ in self._config['params']]

        for i, query in enumerate(self._config['params']):
            query_results = [[] for _ in self._tracer.patterns[i]]
            self._fetch_data(self._config["headers"], query)
            for log_line in self.logs:
                for j, pattern in enumerate(self._tracer.patterns[i]):
                    match = re.search(pattern, log_line[0])
                    if match:
                        match_as_list = list(match.groups())
                        match_as_list.append(log_line[1])
                        match_as_list.append(log_line[2])
                        query_results[j].append(match_as_list)
                        break
            # logger.debug('Fetched lines parsed with pattern')
            results[i].extend(query_results)
            self.logs.clear()

        return results

    def read(self) -> List[pd.DataFrame]:
        # logger.info(f'Reading {self._config["url"]}')

        results = self._make_queries()
        dfs = self._tracer.trace(results)

        return dfs

    def single_query_info(self) -> Result[Dict, Response]:
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

            return Err(response)

    def multi_query_info(self) -> Result[Iterator, str]:
        response = requests.post(self._config['url'], headers=self._config['headers'], params=self._config['params'])
        if response.status_code != 200:
            logger.error(f'Request failed with status code: {response.status_code}')
            return Err(response.text)

        try:
            data = response.iter_lines()
            return Ok(data)
        except json.decoder.JSONDecodeError as e:
            logger.error(f'Failed to decode JSON: {e}')
            logger.error(f'Response content: {response.content}')

            return Err(response.text)
