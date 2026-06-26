# Python Imports
from typing import Self

# Project Imports
from src.analysis.mesh_analysis.analyzers.analyzer import Analyzer
from src.analysis.mesh_analysis.readers.tracers.service_discovery_tracer import ServiceDiscoveryTracer


class ServiceDiscoveryAnalyzer(Analyzer):

    def with_discovery_analysis(self) -> Self:
        return self._with_parameterized_check(
            self._analyze_discovery,
            on_fail="stop"
        )

    def _analyze_discovery(self):
        extra_fields = self.data_puller.kwargs.get("extra_fields")
        tracer = (ServiceDiscoveryTracer()
                  .with_extra_fields(extra_fields)
                  .with_starting_discovery_pattern())

        # TODO: Improve this
        stateful_sets = ["rare-discoverer"]

        # nodes_per_statefulset = self.data_puller.kwargs.get("nodes_per_statefulset", [])
        nodes_per_statefulset = [1]

        dfs = self.data_puller.get_all_node_dataframes(tracer, stateful_sets, nodes_per_statefulset)

        return dfs


