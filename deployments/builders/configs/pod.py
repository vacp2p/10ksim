from copy import deepcopy
from typing import Dict, List, Literal, Optional, TypeVar

from kubernetes.client import (
    V1Container,
    V1ObjectMeta,
    V1PodDNSConfig,
    V1PodSpec,
    V1PodTemplateSpec,
    V1Volume,
)
from pydantic import BaseModel, ConfigDict

from builders.configs.container import ContainerConfig, build_container

T = TypeVar("T")


class PodSpecConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    volumes: Optional[List[V1Volume]] = None
    init_containers: Optional[List[ContainerConfig]] = None
    container_configs: List[ContainerConfig] = []
    dns_config: Optional[V1PodDNSConfig] = None

    def with_dns_service(self, service: str, *, overwrite: bool = False):
        if self.dns_config is None:
            self.dns_config = V1PodDNSConfig(searches=[])

        if service in self.dns_config and not overwrite:
            raise ValueError(
                f"The {type(self)} already has dns service. "
                f"service: `{service}` config: `{self}`"
            )

        self.dns_config.searches.append(service)

    def with_volume(self, volume: V1Volume, *, overwrite: bool = False):
        if self.volumes is None:
            self.volumes = []

        if not overwrite and volume.name in [item.name for item in self.volumes]:
            raise ValueError(
                f"Volume already exists in {type(self)}. volume: `{volume}` config: `{self}`"
            )

        self.volumes.append(volume)

    def add_init_container(
        self, init_container: ContainerConfig | V1Container | dict, *, overwrite: bool = False
    ):
        from builders.helpers import convert_to_container_config

        container_config = convert_to_container_config(init_container)
        if self.init_containers is None:
            self.init_containers = []

        if not overwrite and container_config.name in [item.name for item in self.init_containers]:
            raise ValueError(
                f"InitContainer already exists in {type(self)}. init_container: `{init_container}` "
                f"initContainer_config: `{container_config}` config: `{self}`"
            )

        self.init_containers.append(container_config)

    def add_container(
        self,
        container: ContainerConfig | V1Container | dict,
        *,
        order: Literal["prepend", "append"] = "append",
        overwrite: bool = False,
    ):
        from builders.helpers import convert_to_container_config

        container_config = convert_to_container_config(container)

        if not overwrite and container_config.name in [
            item.name for item in self.container_configs
        ]:
            raise ValueError(
                f"Container already exists in {type(self)}. container: `{container}` "
                f"container_config: `{container_config}` config: `{self}`"
            )

        if order == "append":
            self.container_configs.append(container_config)
        elif order == "prepend":
            self.container_configs.insert(0, container_config)
        else:
            raise ValueError(f"Invalid order. order: `{order}`")


class PodTemplateSpecConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: Optional[str] = None
    namespace: Optional[str] = None
    labels: Dict[str, str] = None
    pod_spec_config: PodSpecConfig = PodSpecConfig()

    def with_app(self, app: str, *, overwrite: bool = False):
        if self.labels is None:
            self.labels = {}

        if not overwrite and app in [value for key, value in self.labels.items()]:
            raise ValueError(
                f'The {type(self)} already has a value for "app" in labels. '
                f"app arg: `{app}` config: `{self}`"
            )

        self.labels["app"] = app


def build_pod_spec(config: PodSpecConfig) -> V1PodSpec:
    containers = []
    for container_config in config.container_configs:
        containers.append(build_container(container_config))

    init_containers = (
        [build_container(init_container_config) for init_container_config in config.init_containers]
        if config.init_containers
        else None
    )

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
