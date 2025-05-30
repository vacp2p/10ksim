# Python Imports
import json
import logging
import re
import pandas as pd
import requests
from typing import Dict, List, Iterator, Optional
from httpx import Response
from result import Result, Ok, Err

# Project Imports
from src.mesh_analysis.readers.tracers.message_tracer import MessageTracer

logger = logging.getLogger(__name__)


class VictoriaReader:
    """
    Note: Queries should follow the same order as the patterns in the Tracer.
    ie:
    tracer = Tracer.with_SENT_pattern_group().with_RECEIVED_pattern_group()
    builder = VictoriaReaderBuilder(tracer, ['SENT QUERY', 'RECEIVED QUERY'])

    or

    tracer = Tracer.with_RECEIVED_pattern_group().with_SENT_pattern_group()
    builder = VictoriaReaderBuilder(tracer, ['RECEIVED QUERY', 'SENT QUERY'])
    """
    def __init__(self, tracer: Optional[MessageTracer], victoria_config_query: Dict):
        self._tracer: MessageTracer = tracer
        self._config_query = victoria_config_query

    def _fetch_data(self, query: Dict, i: int):
        logs = []
        logger.debug(f'Fetching {query}')
        with requests.post(query['url'], headers=query['headers'], params=query['params'][i], stream=True) as response:
            for line in response.iter_lines():
                if line:
                    try:
                        parsed_object = json.loads(line)
                    except json.decoder.JSONDecodeError as e:
                        logger.info(line)
                        exit()
                    logs.append((parsed_object['_msg'],) +
                                tuple(parsed_object[k] for k in self._tracer.get_extra_fields()))
        logger.debug(f'Fetched {len(logs)} log lines')

        return logs

    def _make_queries(self) -> List:
        # In victoria you cannot do group extraction, so we have to parse it "manually"
        # We will consider a result for each group of patterns (ie: different ways to tell we received a message)
        results = [[] for _ in range(self._tracer.get_num_patterns_group())]
        # TODO SOLO HACER FETCH DEL PATTERN QUE SE NECESITA, SI NO SE COMPARA TODO CON TODO?
        for i, patterns in enumerate(self._tracer.patterns):
            query_results = [[] for _ in patterns]
            logs = self._fetch_data(self._config_query, i)
            for log_line in logs:
                for j, pattern in enumerate(patterns):
                    match = re.search(pattern, log_line[0])
                    if match:
                        match_as_list = list(match.groups())
                        match_as_list.extend(log_line[1:])
                        query_results[j].append(match_as_list)
                        break

            results[i].extend(query_results)

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
