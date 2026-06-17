# Python Imports
from copy import deepcopy
from typing import Dict, List, Literal, Optional, TypeVar

from kubernetes.client import (
    V1Container,
    V1ObjectMeta,
    V1Pod,
    V1PodDNSConfig,
    V1PodSecurityContext,
    V1PodSpec,
    V1PodTemplateSpec,
    V1Volume,
)
from pydantic import BaseModel, ConfigDict, Field

# Project Imports
from src.deployments.core.configs.container import ContainerConfig, build_container

T = TypeVar("T")


class PodSpecConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    volumes: Optional[List[V1Volume]] = None
    init_containers: Optional[List[ContainerConfig]] = None
    container_configs: List[ContainerConfig] = []
    dns_config: Optional[V1PodDNSConfig] = None
    service_account_name: Optional[str] = None
    security_context: Optional[V1PodSecurityContext] = None
    automount_service_account_token: Optional[bool] = None

    def with_dns_service(self, service: str, *, overwrite: bool = False):
        if self.dns_config is None:
            self.dns_config = V1PodDNSConfig(searches=[])

        if service in self.dns_config.searches and not overwrite:
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
        from src.deployments.core.configs.helpers.utils import convert_to_container_config

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
        from src.deployments.core.configs.helpers.utils import convert_to_container_config

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

    def with_service_account_name(self, name: str, *, overwrite: bool = False):
        if self.service_account_name is not None and not overwrite:
            raise ValueError(
                f"service_account_name already exists in {type(self)}."
                f"service_account_name: `{name}` config: `{self}`"
            )
        self.service_account_name = name

    def with_security_context(self, context: V1PodSecurityContext, *, overwrite: bool = False):
        if self.security_context is not None and not overwrite:
            raise ValueError(
                f"security_context already exists in {type(self)}."
                f"security_context: `{context}` config: `{self}`"
            )
        self.security_context = context


class PodTemplateSpecConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: Optional[str] = None
    namespace: Optional[str] = None
    labels: Dict[str, str] = None
    annotations: Optional[Dict[str, str]] = None
    pod_spec_config: PodSpecConfig = Field(default_factory=PodSpecConfig)

    def with_annotation(self, key: str, value: str, *, overwrite: bool = False):
        """Add annotation to pod template metadata."""
        if self.annotations is None:
            self.annotations = {}

        if not overwrite and key in self.annotations:
            raise ValueError(
                f"Annotation already exists in {type(self)}. "
                f"key: `{key}` value: `{value}` config: `{self}`"
            )
        self.annotations[key] = value

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
        service_account_name=config.service_account_name,
        security_context=config.security_context,
        automount_service_account_token=config.automount_service_account_token,
    )


def build_pod_template_spec(config: PodTemplateSpecConfig) -> V1PodTemplateSpec:
    return V1PodTemplateSpec(
        metadata=V1ObjectMeta(
            name=config.name,
            namespace=config.namespace,
            labels=config.labels,
            annotations=config.annotations,
        ),
        spec=build_pod_spec(config.pod_spec_config),
    )


class PodConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: Optional[str] = None
    namespace: Optional[str] = None
    labels: Dict[str, str] = None
    kind: Optional[str] = Field(default="Pod")
    pod_spec_config: PodSpecConfig = Field(default_factory=PodSpecConfig)

    def with_app(self, app: str, *, overwrite: bool = False):
        if self.labels is None:
            self.labels = {}

        if not overwrite and app in [value for key, value in self.labels.items()]:
            raise ValueError(
                f'The {type(self)} already has a value for "app" in labels. '
                f"app arg: `{app}` config: `{self}`"
            )

        self.labels["app"] = app


def build_pod(config: PodConfig) -> V1Pod:
    return V1Pod(
        api_version="v1",
        kind=config.kind,
        metadata=V1ObjectMeta(name=config.name, namespace=config.namespace, labels=config.labels),
        spec=build_pod_spec(config.pod_spec_config),
    )
