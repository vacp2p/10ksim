from copy import deepcopy
from typing import List, Optional, Self

from kubernetes.client import (
    V1Container,
    V1LabelSelector,
    V1ObjectMeta,
    V1PersistentVolumeClaim,
    V1PodSpec,
    V1PodTemplateSpec,
    V1Probe,
    V1ResourceRequirements,
    V1StatefulSet,
    V1StatefulSetSpec,
)
from pydantic import PositiveInt

from deployment.dict_builders.configs import (
    ContainerConfig,
    PodSpecConfig,
    PodTemplateSpecConfig,
    StatefulSetConfig,
)
from deployment.dict_builders.waku import build_command
from deployment.dict_builders.presets import Addrs, Enr, StoreNodes, WakuBootstrapNode, WakuNode
from deployment.dict_builders.helpers import WAKU_COMMAND_STR, extend_container_command_args, find_waku_container_config


def build_stateful_set(config: StatefulSetConfig) -> V1StatefulSet:
    return V1StatefulSet(
        api_version=config.apiVersion,
        kind=config.kind,
        metadata=V1ObjectMeta(name=config.name, namespace=config.namespace, labels=config.labels),
        spec=V1StatefulSetSpec(
            replicas=config.stateful_set_spec.replicas,
            pod_management_policy=config.pod_management_policy,
            selector=V1LabelSelector(match_labels=config.stateful_set_spec.selector_labels),
            service_name=config.stateful_set_spec.service_name,
            template=build_pod_template_spec(config.stateful_set_spec.pod_template_spec_config),
            volume_claim_templates=config.stateful_set_spec.volume_claim_templates,
        ),
    )


class StatefulSetBuilder:
    config: StatefulSetConfig

    def __init__(self, config: StatefulSetConfig):
        self.config = config

    def with_replicas(self, replicas: int) -> Self:
        self.config.replicas = replicas
        return self

    def with_label(self, key: str, value: str) -> Self:
        self.config.labels[key] = value
        self.config.selector_labels[key] = value
        self.config.pod_template_spec_config.labels[key] = value
        return self

    def with_volume_claim_template(self, pvc: V1PersistentVolumeClaim) -> Self:
        if self.config.volume_claim_templates is None:
            self.config.volume_claim_templates = []
        self.config.volume_claim_templates.append(pvc)
        return self

    def build(self) -> V1StatefulSet:
        return build_stateful_set(self.config)


class WakuStatefulSetBuilder(StatefulSetBuilder):

    def __init__(self, config: StatefulSetConfig):
        super().__init__(config)

    # def with_bootsrap()

    def build(self):
        if not self.config.name:
            raise ValueError("Must configure node first.")
        return super().build()

    def with_waku_config(self, name: str, namespace: str) -> Self:
        self.config.name = name
        self.config.namespace = namespace
        self.config.apiVersion = "apps/v1"
        self.config.kind = "StatefulSet"
        self.config.pod_management_policy = "Parallel"
        self.config.stateful_set_spec = WakuNode.create_stateful_set_spec_config()
        return self

    def with_store(self) -> Self:
        StoreNodes.stateful_set(self.config)
        return self

    def with_args(self, args: List[str]) -> Self:
        extend_container_command_args(self.config, "waku", WAKU_COMMAND_STR, args)
        return self

    def with_enr(self, num: int, service_names: List[str]) -> Self:
        Enr.pod_spec(
            self.config.stateful_set_spec.pod_template_spec_config.pod_spec_config,
            num=num,
            service_names=service_names,
        )
        return self


def build_container(config: ContainerConfig) -> V1Container:
    return V1Container(
        name=config.name,
        image=str(config.image),
        image_pull_policy=config.image_pull_policy,
        ports=deepcopy(config.ports),
        env=deepcopy(config.env),
        resources=deepcopy(config.resources),
        readiness_probe=deepcopy(config.readiness_probe),
        volume_mounts=deepcopy(config.volume_mounts),
        command=build_command(config.command_config),
    )


class ContainerBuilder:
    config: ContainerConfig

    def __init__(self, config: ContainerConfig):
        self.config = config

    def build(self) -> V1Container:
        return build_container(self.config)

    def with_command(self, command: List[str]) -> Self:
        for line in command:
            self.config.command_config.with_command(command=line, args=[], multiline=False)
        return self

    def with_readiness_probe(self, probe: V1Probe) -> Self:
        self.config.with_readines_probe(probe)
        return self

    def with_resources(self, resources: V1ResourceRequirements) -> Self:
        self.config.resources = resources
        return self


class WakuContainerBuilder(ContainerBuilder):
    def __init__(self, config: ContainerConfig):
        super.__init__(config)

    def with_bootstrap_nodes(self) -> Self:
        raise NotImplementedError()
        return self

    def with_store(self) -> Self:
        StoreNodes.container(self.config)
        return self

    def with_node_resources(self):
        return self.with_resources(WakuBootstrapNode.create_resources())

    def with_bootstrap_resources(self):
        res = V1ResourceRequirements(
            requests={"memory": "64Mi", "cpu": "50m"}, limits={"memory": "768Mi", "cpu": "400m"}
        )
        return self.with_resources(res)


def build_pod_spec(config: PodSpecConfig) -> V1PodSpec:
    containers = []
    for container_config in config.container_configs:
        containers.append(build_container(container_config))

    init_containers = [
        build_container(init_container_config) for init_container_config in config.init_containers
    ] or None

    return V1PodSpec(
        containers=containers,
        init_containers=deepcopy(init_containers),
        volumes=deepcopy(config.volumes),
        dns_config=deepcopy(config.dns_config),
    )


def build_pod_template_spec(config: PodTemplateSpecConfig) -> V1PodTemplateSpec:
    return V1PodTemplateSpec(
        metadata=V1ObjectMeta(name=config.name, namespace=config.namespace, labels=config.labels),
        spec=build_pod_spec(config.pod_spec_config),
    )


class PodSpecBuilder:
    config: PodSpecConfig

    def __init__(self, config: PodSpecConfig):
        self.config = config

    def build(self) -> V1PodSpec:
        return build_pod_spec(self.config)

    def add_container(self, container: ContainerConfig | V1Container | dict):
        self.config.add_container(container)
        return self

    def with_container_config(self, container: ContainerConfig) -> Self:
        self.config.add_container(container)
        return self


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
        StoreNodes.pod_spec(self.config)
        return self

    def with_enr(
        self,
        num: PositiveInt,
        service_names: List[str],
        *,
        init_container_image: Optional[str] = None,
    ) -> Self:
        Enr.pod_spec(self.config)
        return self

    def with_addr(
        self,
        num: PositiveInt,
        service_names: List[str],
        *,
        init_container_image: Optional[str] = None,
    ) -> Self:
        Addrs.pod_spec(self.config)
        return self

    def with_bootstrap(self) -> Self:
        raise NotImplementedError()
        return self

    # TODO
    # def with_health_probe(self) -> Self:
    #     self._container_builder.with_readiness_probe("health")
    #     return self

    # def with_metrics_probe(self) -> Self:
    #     self._container_builder.with_readiness_probe("metrics")
    #     return self
