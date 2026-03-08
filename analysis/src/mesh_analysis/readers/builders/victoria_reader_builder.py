# Python Imports
from typing import List, Optional, Self, Union

from pydantic import BaseModel, Field

# Project Imports
from src.mesh_analysis.readers.tracers.message_tracer import MessageTracer
from src.mesh_analysis.readers.tracers.waku_tracer import NewTracer, WakuTracer
from src.mesh_analysis.readers.victoria_reader import NewVictoriaReader, VictoriaReader


class VictoriaQueryBuilder(BaseModel):
    filters : List[str] = Field(default_factory=list)
    uniq_by : Optional[str] = None
    queries : List[str] = Field(default_factory=list)
    url : Optional[str] = None

    def _get_filters(self, kwargs) -> List[str]:
        filters = [
            lambda : f"kubernetes.container_name:{kwargs['container_name']} ",
            lambda : f"kubernetes.pod_namespace:{kwargs['namespace']} ",
            lambda : f"_time:[{kwargs['start_time']}, {kwargs['end_time']}]",
        ]
        result = []
        for filter in filters:
            try:
                result.append(filter())
            except KeyError:
                pass
        return result

    def with_filters(self, kwargs) -> Self:
        self.filters.extend(self._get_filters(kwargs))
        return self

    def with_url(self, url)->Self:
        self.url = url
        return self

    def with_stateful_set(self, name, index) -> Self:
        self.filters.append(f"kubernetes.pod_name:{name}-{index if index is not None else ''} ")
        return self

    def with_pod_identifier(self, pod_name: str) -> Self:
        self.filters.append(f"kubernetes.pod_name:{pod_name} ")
        return self

    def with_query(self, query) -> Self:
        self.queries.append(query)
        return self

    def with_unique_by(self, uniq_by)->Self:
        if uniq_by.startswith("|"):
            uniq_by = uniq_by[1:]
        self.uniq_by = uniq_by
        return self

    def _build(self, query)->dict:
        full_query = " AND ".join((line for line in self.filters + [query]))
        if self.uniq_by:
            full_query += "|" + self.uniq_by
        return {"query":full_query}

    def build_query_config(self)->dict:
        queries = [
            self._build(query)
        for query in self.queries
        ]
        if len(queries) == 1:
            queries = queries[0]
        return {"url": self.url,
                                 "headers": {"Content-Type": "application/json"},
                                 "params": queries
                                 }


class VictoriaReaderBuilder(BaseModel):
    kwargs : dict
    tracer : object
    queries :List[str]= Field(default_factory=list)
    extra_fields : Optional[List[str]] = None

    def _query_builder(self, uniq_by : Optional[str]=None) -> VictoriaQueryBuilder:
        query_builder = VictoriaQueryBuilder().with_url(self.kwargs['url']).with_filters(self.kwargs)
        if uniq_by:
            query_builder.with_unique_by(uniq_by)
        for query in self.queries:
            query_builder.with_query(query)
        return query_builder

    def build_with_pod_identifier(self, pod_name: str, uniq_by: Optional[str] = None) -> NewVictoriaReader:
        query_builder = self._query_builder(uniq_by).with_pod_identifier(pod_name)
        query = query_builder.build_query_config()
        return NewVictoriaReader(self.tracer, query, extra_fields=self.extra_fields)

    # TODO: rename this
    def build_with_queries(self, stateful_set_name: str, node_index: Optional[int] = None, uniq_by: Optional[str] = None) -> NewVictoriaReader:
        query_builder = self._query_builder(uniq_by).with_stateful_set(stateful_set_name, node_index)
        return NewVictoriaReader(self.tracer, query_builder.build_query_config(), extra_fields=self.extra_fields)


    def build_with_single_query(self, pod_name: str, uniq_by: Optional[str] = None) -> NewVictoriaReader:
        query_builder = self._query_builder(uniq_by).with_pod_identifier(pod_name)
        return NewVictoriaReader(self.tracer, query_builder.build_query_config(), extra_fields=self.extra_fields)
