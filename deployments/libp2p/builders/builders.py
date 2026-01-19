from typing import Self

from kubernetes.client import V1StatefulSet
from pydantic import PositiveInt

from core.builders import StatefulSetBuilder
from libp2p.builders.nodes import Nodes


class Libp2pStatefulSetBuilder(StatefulSetBuilder):

    def build(self) -> V1StatefulSet:
        if not self.config.name:
            raise ValueError(f"Must configure node first. Config: `{self.config}`")
        return super().build()

    def with_libp2p_config(
        self,
        name: str,
        namespace: str,
        num_nodes: PositiveInt,
    ) -> Self:
        self.config.name = name
        self.config.namespace = namespace
        self.config.pod_management_policy = "Parallel"
        self.config.stateful_set_spec = Nodes.create_stateful_set_spec_config(
            namespace=namespace,
        )
        self.config.stateful_set_spec.replicas = num_nodes

        return self
