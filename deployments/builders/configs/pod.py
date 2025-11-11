from typing import Dict, List, Literal, Optional, TypeVar

from kubernetes.client import (
    V1Container,
    V1PodDNSConfig,
    V1Volume,
)
from pydantic import BaseModel, ConfigDict

from builders.configs.container import ContainerConfig

T = TypeVar("T")


class PodSpecConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    volumes: Optional[List[V1Volume]] = None
    init_containers: Optional[List[ContainerConfig]] = None
    container_configs: List[ContainerConfig] = []
    dns_config: Optional[V1PodDNSConfig] = None

    def with_dns_service(self, service: str, *, overwrite=False):
        if self.dns_config is None:
            self.dns_config = V1PodDNSConfig(searches=[])

        if service in self.dns_config and overwrite == False:
            raise ValueError(
                f"PodSpecConfig already has dns service. service: `{service}` config: `{self}`"
            )

        self.dns_config.searches.append(service)

    def with_volume(self, volume: V1Volume):
        if self.volumes is None:
            self.volumes = []
        self.volumes.append(volume)

    def add_init_container(self, init_container: ContainerConfig | V1Container | dict):
        from builders.helpers import convert_to_container_config

        container_config = convert_to_container_config(init_container)
        if self.init_containers is None:
            self.init_containers = []
        self.init_containers.append(container_config)

    def add_container(
        self,
        container: ContainerConfig | V1Container | dict,
        *,
        order: Literal["prepend", "append"] = "append",
    ):
        from builders.helpers import convert_to_container_config

        container_config = convert_to_container_config(container)
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

    def with_app(self, app):
        if self.labels is None:
            self.labels = {}
        self.labels["app"] = app
