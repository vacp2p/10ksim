# Python Imports
from typing import List, Optional, Union

# Project Imports
from src.mesh_analysis.readers.victoria_reader import VictoriaReader


class VictoriaReaderBuilder:
    """Builder for Victoria Reader. This allows us to build a reader per Node when parallelizing the
    queries, having access to custom  queries per node while maintaining decoupled the building of the Reader
    class from the StackAnalysis class.
    Note: Queries must follow the same order as the Tracer patterns.
    """
    def __init__(self, tracer, queries: Union[List[str], str], **kwargs):
        self._kwargs = kwargs
        self._tracer = tracer
        self._queries = queries

    def build_with_pod_identifier(self, pod_name: str, uniq_by: Optional[str] = None) -> VictoriaReader:

        query = {"query": f"kubernetes.container_name:{self._kwargs['container_name']} "
                                f"AND kubernetes.pod_name:{pod_name} "
                                f"AND kubernetes.pod_namespace:{self._kwargs['namespace']} "
                                f"AND _time:[{self._kwargs['start_time']}, {self._kwargs['end_time']}]"
                                f"{uniq_by if uniq_by is not None else ''}"}

        victoria_config_query = {"url": self._kwargs['url'],
                                 "headers": {"Content-Type": "application/json"},
                                 "params": [query]
                                 }

        reader = VictoriaReader(self._tracer, victoria_config_query)

        return reader

    def build_with_queries(self, stateful_set_name: str, node_index: Optional[int] = None, uniq_by: Optional[str] = None) -> VictoriaReader:
        params = []
        for query in self._queries:
            params.append({"query": f"kubernetes.container_name:{self._kwargs['container_name']} "
                                    f"AND kubernetes.pod_name:{stateful_set_name}-{node_index if node_index is not None else ''} "
                                    f"AND kubernetes.pod_namespace:{self._kwargs['namespace']} "
                                    f"AND {query} "
                                    f"AND _time:[{self._kwargs['start_time']}, {self._kwargs['end_time']}]"
                                    f"{uniq_by if uniq_by is not None else ''}"})

        victoria_config_query = {"url": self._kwargs['url'],
                                 "headers": {"Content-Type": "application/json"},
                                 "params": params
                                 }

        reader = VictoriaReader(self._tracer, victoria_config_query)

        return reader

    def build_with_single_query(self, pod_name: str, uniq_by: Optional[str] = None) -> VictoriaReader:

        param = {"query": f"kubernetes.container_name:{self._kwargs['container_name']} "
                                f"AND kubernetes.pod_name:{pod_name} "
                                f"AND kubernetes.pod_namespace:{self._kwargs['namespace']} "
                                f"AND {self._queries} "
                                f"AND _time:[{self._kwargs['start_time']}, {self._kwargs['end_time']}]"
                                f"{uniq_by if uniq_by is not None else ''}"}

        victoria_config_query = {"url": self._kwargs['url'],
                                 "headers": {"Content-Type": "application/json"},
                                 "params": param
                                 }

        reader = VictoriaReader(self._tracer, victoria_config_query)

        return reader
