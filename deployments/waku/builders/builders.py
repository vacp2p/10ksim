from typing import List, Literal, Optional, Self

from kubernetes.client import V1PodSpec, V1Probe
from pydantic import PositiveInt

from core.builders import ContainerBuilder, PodSpecBuilder, StatefulSetBuilder
from core.configs.container import ContainerConfig, Image
from core.configs.helpers import with_container_command_args
from core.configs.pod import PodSpecConfig
from waku.builders import bootstrap as WakuBootstrapNode
from waku.builders import store as Store
from waku.builders.enr_or_addr import Addrs, Enr
from waku.builders.helpers import WAKU_COMMAND_STR, find_waku_container_config
from waku.builders.nodes import Nodes
from waku.builders.regression import RegressionNodes


class WakuContainerBuilder(ContainerBuilder):
    def __init__(self, config: ContainerConfig):
        super.__init__(config)

    def with_bootstrap_nodes(self) -> Self:
        WakuBootstrapNode.apply_container_config(self.config, overwrite=True)
        self.with_args(WakuBootstrapNode.create_args())
        return self

    def with_store(self) -> Self:
        Store.apply_container_config(self.config)
        return self

    def with_node_resources(self):
        return self.with_resources(Nodes.create_resources())

    def with_bootstrap_resources(self):
        return self.with_resources(WakuBootstrapNode.create_resources())


class WakuPodSpecBuilder(PodSpecBuilder):
    config: PodSpecConfig

    def __init__(self, config: PodSpecConfig):
        self.config = config

    def build(self) -> V1PodSpec:
        return super().build()

    def with_readiness_probe(self, readiness_probe: V1Probe) -> Self:
        waku_container_config = find_waku_container_config(self.config.container_configs)
        waku_container_config.with_readiness_probe(readiness_probe)
        return self

    def with_store(self) -> Self:
        Store.apply_pod_spec_config(self.config)
        return self

    def with_enr(
        self,
        num: PositiveInt,
        service_names: List[str],
        init_container_image: Optional[Image] = None,
    ) -> Self:
        Enr.pod_spec(self.config, num, service_names, init_container_image)
        return self

    def with_addr(
        self,
        num: PositiveInt,
        service_names: List[str],
        init_container_image: Optional[Image] = None,
    ) -> Self:
        Addrs.pod_spec(self.config, num, service_names, init_container_image)
        return self


class WakuStatefulSetBuilder(StatefulSetBuilder):

    def build(self):
        if not self.config.name:
            raise ValueError(f"Must configure node first. Config: `{self.config}`")
        return super().build()

    def with_waku_config(self, name: str, namespace: str, num_nodes: PositiveInt) -> Self:
        self.config.name = name
        self.config.namespace = namespace
        self.config.apiVersion = "apps/v1"
        self.config.kind = "StatefulSet"
        self.config.pod_management_policy = "Parallel"
        self.config.stateful_set_spec = Nodes.create_stateful_set_spec_config(namespace)
        self.config.stateful_set_spec.replicas = num_nodes
        return self

    def with_regression(self) -> Self:
        if not self.config.name:
            raise ValueError(f"Must configure node first. Config: `{self.config}`")
        self.with_args(RegressionNodes.create_args())
        self.with_enr(3, [f"zerotesting-bootstrap.{self.config.namespace}"])
        container = find_waku_container_config(self.config)
        container.with_resources(Nodes.create_resources())
        return self

    def with_bootstrap(self) -> Self:
        if not self.config.name:
            raise ValueError(f"Must configure node first. Config: `{self.config}`")
        WakuBootstrapNode.apply_stateful_set_config(
            self.config, self.config.namespace, overwrite=True
        )
        self.with_args(WakuBootstrapNode.create_args())
        return self

    def with_store(self) -> Self:
        Store.apply_stateful_set_config(self.config)
        return self

    def with_nice_command(self, increment: int) -> Self:
        """Runs node with cpu priority.

        :param increment:
            Positive: Lower priority.
            Zero: The default priority for processes.
            Negative: Higher priority.
        """
        Nodes.apply_nice_command(self.config, increment)
        return self

    def with_args(
        self,
        args: List[str],
        *,
        on_duplicate: Literal["error", "ignore", "replace"] = "error",
    ) -> Self:
        with_container_command_args(
            self.config, "waku", WAKU_COMMAND_STR, args, on_duplicate=on_duplicate
        )
        return self

    def with_enr(
        self,
        num: int,
        service_names: List[str] | str,
        init_container_image: Optional[Image] = None,
    ) -> Self:
        if isinstance(service_names, str):
            service_names = [service_names]
        Enr.pod_spec(
            self.config.stateful_set_spec.pod_template_spec_config.pod_spec_config,
            num=num,
            service_names=service_names,
            init_container_image=init_container_image,
        )
        return self
