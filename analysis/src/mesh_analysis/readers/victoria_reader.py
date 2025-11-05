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
from src.mesh_analysis.readers.reader import Reader
from src.mesh_analysis.readers.tracers.message_tracer import MessageTracer

logger = logging.getLogger(__name__)


class VictoriaReader(Reader):
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
        """
        :param tracer: MessageTracer instance to retrieve raw message patterns from Victoria.
        :param victoria_config_query: Configuration for the Victoria query. This allows to do a first filtering by the
        monitoring stack retrieving only the lines we are interested in, saving time in the parsing process.
        """
        self._tracer: MessageTracer = tracer
        self._config_query = victoria_config_query

    def _fetch_data(self, url: str, headers: Dict, params: Dict):
        logs = []
        logger.debug(f'Fetching {params}')
        with requests.post(url=url, headers=headers, params=params, stream=True) as response:
            for line in response.iter_lines():
                if line:
                    try:
                        parsed_object = json.loads(line)
                    except json.decoder.JSONDecodeError as e:
                        logger.info(line)
                        exit()
                    logs.append((parsed_object['_msg'],) +
                                tuple(parsed_object[k] for k in self._tracer.get_extra_fields() or []))
        logger.debug(f'Fetched {len(logs)} log lines')

        return logs

    def make_queries(self) -> List:
        """
        This function returns a list of lists, structured hierarchically as follows:
        - The outer list corresponds to the pattern groups.
        - Each element in the outer list is a list representing a specific pattern group.
        - Within each pattern group list, there are sublists, one for each pattern in that group.
        - Each sublist contains the lines that match the corresponding pattern.

        The result is organized as [pattern_groups -> patterns -> matched_lines], where:
        - Each pattern group can have multiple patterns.
        - Each pattern can match multiple lines.
        """
        params = self._config_query['params']
        if isinstance(params, Dict):
            params = [params]

        results = [[] for _ in range(self._tracer.get_num_patterns_group())]
        for i, patterns in enumerate(self._tracer.patterns):
            query_results = [[] for _ in patterns]
            logs = self._fetch_data(self._config_query['url'],
                                    self._config_query['headers'],
                                    params[i])
            for log_line in logs:
                for j, pattern in enumerate(patterns):
                    match = re.search(pattern, log_line[0])
                    if match:
                        match_as_list = list(match.groups())
                        match_as_list.extend(log_line[1:])
                        query_results[j].append(match_as_list)

            results[i].extend(query_results)

        return results

    def get_dataframes(self) -> List[pd.DataFrame]:
        results = self.make_queries()
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

    def multiline_query_info(self) -> Result[Iterator, str]:
        response = requests.post(self._config_query['url'], headers=self._config_query['headers'], params=self._config_query['params'])
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
