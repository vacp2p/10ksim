# Python Imports
import json
import logging
import re
import pandas as pd
import requests
from typing import Dict, List, Iterator
from httpx import Response
from result import Result, Ok, Err

# Project Imports
from src.mesh_analysis.readers.tracers.message_tracer import MessageTracer


logger = logging.getLogger(__name__)


class VictoriaReader:

    def __init__(self, tracer: MessageTracer, victoria_config_query: Dict, extra_fields: List[str]):
        self._tracer: MessageTracer = tracer
        self._config_query = victoria_config_query
        self.logs = []

    def _fetch_data(self, query: Dict):
        logger.debug(f'Fetching {query}')
        with requests.post(**query, stream=True) as response:
            for line in response.iter_lines():
                if line:
                    try:
                        parsed_object = json.loads(line)
                    except json.decoder.JSONDecodeError as e:
                        logger.info(line)
                        exit()
                    # TODO extract "extra fields" if required just once
                    self.logs.append((parsed_object['_msg'], parsed_object['kubernetes.pod_name'], parsed_object['kubernetes.pod_node_name']))
        logger.debug(f'Fetched {len(self.logs)} messages')

    def _make_queries(self) -> List:
        # In victoria you cannot do group extraction, so we have to parse it "manually"
        # We will consider a result for each group of patterns (ie: different ways to tell we received a message)
        results = [[] for _ in range(self._tracer.get_num_patterns())]

        for i, patterns in enumerate(self._tracer.patterns):
            query_results = [[] for _ in self._tracer.patterns[i]]
            self._fetch_data(self._config_query)
            for log_line in self.logs:
                for j, pattern in enumerate(self._tracer.patterns[i]):
                    match = re.search(pattern, log_line[0])
                    if match:
                        match_as_list = list(match.groups())
                        # TODO check line34 todo, append them once as we are just working with the same container/pod
                        match_as_list.append(log_line[1])
                        match_as_list.append(log_line[2])
                        query_results[j].append(match_as_list)
                        break

            results[i].extend(query_results)
            self.logs.clear()

        return results

    def read_logs(self) -> List[pd.DataFrame]:
        results = self._make_queries()
        dfs = self._tracer.trace(results)

        return dfs

    def single_query_info(self) -> Result[Dict, Response]:
        response = requests.post(**self._config_query)
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
        response = requests.post(**self._config_query)
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
