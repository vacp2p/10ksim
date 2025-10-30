import logging
from abc import abstractmethod
from copy import deepcopy
from pathlib import Path
from typing import List, Self

import pandas as pd
from pandas import DataFrame
from result import Err, Ok

from src.mesh_analysis.readers.builders.victoria_reader_builder import VictoriaReaderBuilder
from src.mesh_analysis.readers.tracers.message_tracer import MessageTracer
from src.mesh_analysis.readers.tracers.nimlibp2p_tracer import Nimlibp2pTracer
from src.mesh_analysis.stacks.stack_analysis import StackAnalysis
from src.mesh_analysis.stacks.vaclab_stack_analysis import VaclabStackAnalysis
from src.utils import file_utils, path_utils

logger = logging.getLogger(__name__)


class BasicTracer(MessageTracer):
    def __init__(self, extra_fields):
        super().__init__(extra_fields)
        self._tracings = []
        self._patterns = []

    @property
    def patterns(self) -> List[List[str]]:
        return self._patterns

    def get_extra_fields(self) -> List[str]:
        return self._extra_fields

    def get_num_patterns_group(self) -> int:
        return len(self._patterns)

    def get_patterns(self) -> List[List[str]]:
        return self._patterns

    def trace(self, parsed_logs: List[List]) -> List[List]:
        """Returns one Dataframe per pattern string. ie: received patterns (2) and sent patterns (2), will
        return a List with 2 positions (received + send patterns). Inside each position, it will have as
        many Dataframes as string patterns there are. In total, 4 Dataframes.
        """

        o_index = 0
        for tracers, log_group in zip(self._tracings, parsed_logs):
            i_index = 0
            logger.debug(f"LOG_GROUP {o_index}-{i_index}: {log_group}")
            for tracer, log in zip(tracers, log_group):
                result = tracer(log)
                logger.debug(f"LOG:: {o_index}-{i_index}: {log}")
                logger.debug(f"REGEX {o_index}-{i_index}: {tracer.__name__}")
                logger.debug(f"RESULT {o_index}-{i_index}: {result}")

                i_index += 1
            o_index += 1

        return [
            [tracer(log) for tracer, log in zip(tracers, log_group)]
            for tracers, log_group in zip(self._tracings, parsed_logs)
        ]


class CustomTracer(BasicTracer):

    def __init__(self, extra_fields):
        super().__init__(extra_fields)
        self._tracings = []
        self._patterns = []

    def with_failure_group(self) -> Self:
        # r'Failed to send message to next hop: tid=12 err="failed new dial: failed getOutgoingSlot in internalConnect: Too many connections'
        # r'Failed to dial next hop: tid=12 err="failed new dial: Unable to establish outgoing link in internalConnect"'
        # TODO: add warning

        self._patterns.append(
            [
                r"ERR (.*?)Failed.*?(failed new dial: failed getOutgoingSlot in internalConnect: Too many connections)",
                r"ERR (.*?)Failed.*?(failed new dial: Unable to establish outgoing link in internalConnect)",
                r"ERR (.*?)(Failed.*)",
            ]
        )

        self._tracings.append(
            [
                self._trace_fail_in_logs,
                self._trace_fail_in_logs,
                self._trace_fail_in_logs,
            ]
        )

        return self

    def _trace_fail_in_logs(self, parsed_logs: List) -> pd.DataFrame:
        columns = ["utc", "error"]
        if self._extra_fields is not None:
            columns.extend(self._extra_fields)
        return pd.DataFrame(parsed_logs, columns=columns)


def _assert_num_nodes(tracer: MessageTracer, kwargs: dict) -> None:
    query = "*"

    reader_builder = VictoriaReaderBuilder(tracer, query, **kwargs)
    stack_analysis = VaclabStackAnalysis(reader_builder, **kwargs)

    num_nodes_per_ss = stack_analysis.get_number_nodes()
    for i, num_nodes in enumerate(num_nodes_per_ss):
        logger.info(f"{num_nodes} == {kwargs['nodes_per_statefulset'][i]}")
        assert (
            num_nodes == kwargs["nodes_per_statefulset"][i]
        ), f"Number of nodes in cluster {num_nodes_per_ss} doesnt match"
        f'with provided {kwargs["nodes_per_statefulset"]} data.'


class BaseAnalyzer:

    dataframe_paths: List[str]
    queries: List[str]
    df_handlers: list
    _kwargs: dict
    extra_fields: List[str] = None

    analysis: StackAnalysis

    @abstractmethod
    def stackanalysis(self) -> StackAnalysis:
        pass

    def __init__(
        self, dump_analysis_dir: str = None, local_folder_to_analyze: str = None, **kwargs
    ):
        self._set_up_paths(dump_analysis_dir, local_folder_to_analyze)
        self._kwargs = kwargs
        self.extra_fields = self._kwargs.get("extra_fields", self.extra_fields)
        self.analysis = self.stackanalysis()

    def _set_up_paths(self, dump_analysis_dir: str, local_folder_to_analyze: str):
        self._dump_analysis_path = Path(dump_analysis_dir) if dump_analysis_dir else None
        result = path_utils.prepare_path_for_folder(self._dump_analysis_path)
        if result.is_err():
            logger.error(result.err_value)
            exit(1)

    def analyze(self, n_jobs: int):
        dfs = self.scrape(n_jobs)

    def dump(self, dfs: List[pd.DataFrame], dump_path):
        logger.info("Dumping dataframes")
        if len(self.dataframe_paths) != len(dfs):
            logger.warning(
                f"Number of dataframe_paths does not match number of dataframes. dataframe_paths: {self.dataframe_paths} (len: {len(self.dataframe_paths)}) vs len(dfs): {len(dfs)}"
            )
        for index, path in enumerate(self.dataframe_paths):
            df = dfs[index].reset_index()
            df = df.astype(str)
            result = file_utils.dump_df_as_csv(df, dump_path / "summary" / f"{path}.csv", False)
            if result.is_err():
                logger.error(result.err_value)
                return Err(result.err_value)

    def load(self, local_data_folder):
        logger.info("loading local data")
        return [
            pd.read_csv(local_data_folder / "summary" / f"{path}.csv")
            for path in self.dataframe_paths
        ]

    def scrape(self, n_jobs, *, force=False) -> List[DataFrame]:
        if self._dump_analysis_path is None:
            return self._scrape(n_jobs)

        cache_dir = Path(self._dump_analysis_path)
        if not cache_dir.exists():
            cache_dir.mkdir(parents=True)

        if not force:
            try:
                cached = self.load(cache_dir)
                return cached
            except:
                pass

        dfs = self._scrape(n_jobs)
        self.dump(dfs, cache_dir)
        return dfs

    def pre_validate_data(self):
        # self._assert_num_nodes()
        pass

    def _scrape(self, n_jobs):
        self.pre_validate_data()
        dfs = self.analysis.get_all_node_dataframes(n_jobs)
        dfs = self._merge_dfs(dfs)
        return dfs

    @abstractmethod
    def _merge_dfs(self, dfs: List[List[pd.DataFrame]]) -> List[pd.DataFrame]:
        pass


def merge_nth_list_of_dfs(
    dfs, columns, *, pod=None, query=None, pattern=None, result=None
) -> DataFrame:
    merged_df = None

    _pods = [dfs[pod]] if pod is not None else dfs
    for _pod in _pods:
        _queries = [_pod[query]] if query is not None else _pod
        for _query in _queries:
            _patterns = [_query[pattern]] if pattern is not None else _query
            for _pattern in _patterns:
                if merged_df is None:
                    merged_df = deepcopy(_pattern)
                else:
                    logger.debug(f"merging:\n{merged_df}\n{_pattern}")
                    merged_df = pd.merge(merged_df, _pattern, on=columns, how="outer")

    return merged_df


class CustomAnalyzer(BaseAnalyzer):

    dataframe_paths: list = ["too_many_connections", "internal_connect_fail", "any_failure"]

    queries: list = [
        "*Failed*",
        # "WRN", # TODO
    ]

    extra_fields: List[str] = ["kubernetes.pod_name"]

    def stackanalysis(self) -> StackAnalysis:
        self.tracer = CustomTracer(extra_fields=self._kwargs["extra_fields"]).with_failure_group()
        self.reader_builder = VictoriaReaderBuilder(self.tracer, self.queries, **self._kwargs)
        return VaclabStackAnalysis(self.reader_builder, **self._kwargs)

    def analyze(self, n_jobs: int) -> dict:
        dfs = self.scrape(n_jobs, force=False)

        results_dict = {}

        too_many_connections = dfs[0]
        if not too_many_connections.empty:
            counts_str = "\n".join(
                [
                    f"{item[0]}: {item[1]}"
                    for item in too_many_connections.groupby(["kubernetes.pod_name"]).size().items()
                ]
            )
            logger.error(f'"Too many connections" failure found ❌')
            logger.error(f"too_many_connections error found in the following pods:\n{counts_str}")
            results_dict["too_many_connections"] = Err(len(too_many_connections))
        else:
            logger.error(f'"Too many connections" failure not found ✅')
            results_dict["too_many_connections"] = Ok(None)

        failed_to_connect = dfs[1]
        if not failed_to_connect.empty:
            counts_str = "\n".join(
                [
                    f"{item[0]}: {item[1]}"
                    for item in failed_to_connect.groupby(["kubernetes.pod_name"]).size().items()
                ]
            )
            logger.error(f"failed_to_connect error found in the following pods:\n{counts_str}")
            logger.error(f'"Unable to establish outgoing link" failure found ❌')
            results_dict["failed_to_connect"] = Err(len(failed_to_connect))
        else:
            logger.error(f'"Unable to establish outgoing link" failure not found ✅')
            results_dict["failed_to_connect"] = Ok(None)

        any_failure = dfs[2]
        if not any_failure.empty:
            counts_str = "\n".join(
                [
                    f"{item[0]}: {item[1]}"
                    for item in any_failure.groupby(["kubernetes.pod_name"]).size().items()
                ]
            )
            logger.error(f"Failure found ❌")
            logger.error(f"Failures found in the following pods:\n{counts_str}")
            results_dict["any_failure"] = Err(len(any_failure))
        else:
            logger.error(f"No failures found ✅")
            results_dict["any_failure"] = Ok(None)

        return results_dict

    def pre_validate_data(self):
        tracer = Nimlibp2pTracer().with_wildcard_pattern()
        _assert_num_nodes(tracer, self._kwargs)

    def _merge_dfs(self, dfs: List[List[List[pd.DataFrame]]]) -> List[pd.DataFrame]:
        logger.info("Merging and sorting information")
        too_many_connections_df = merge_nth_list_of_dfs(
            dfs, ["kubernetes.pod_name", "kubernetes.pod_node_name", "utc", "error"], pattern=0
        )
        internal_connect_fail_df = merge_nth_list_of_dfs(
            dfs, ["kubernetes.pod_name", "kubernetes.pod_node_name", "utc", "error"], pattern=1
        )
        any_fail = merge_nth_list_of_dfs(
            dfs, ["kubernetes.pod_name", "kubernetes.pod_node_name", "utc", "error"], pattern=2
        )
        return [too_many_connections_df, internal_connect_fail_df, any_fail]
