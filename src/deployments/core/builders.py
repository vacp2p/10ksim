import logging
from typing import List, Optional, Self, Tuple, Union

from kubernetes.client import (
    V1Container,
    V1PersistentVolumeClaim,
    V1Pod,
    V1PodSpec,
    V1PodTemplateSpec,
    V1Probe,
    V1ResourceRequirements,
    V1Service,
    V1ServicePort,
    V1StatefulSet,
)
from pydantic import BaseModel, Field, NonNegativeInt

from src.deployments.core.configs.command import Command, CommandConfig, build_command
from src.deployments.core.configs.container import ContainerConfig, Image, build_container
from src.deployments.core.configs.helpers.utils import (
    init_container_bandwidth_limit,
    init_container_delay,
    with_image_for_container,
)
from src.deployments.core.configs.pod import (
    PodConfig,
    PodSpecConfig,
    PodTemplateSpecConfig,
    build_pod,
    build_pod_spec,
    build_pod_template_spec,
)
from src.deployments.core.configs.service import ServiceConfig, ServiceSpecType, build_service
from src.deployments.core.configs.statefulset import StatefulSetConfig, build_stateful_set

logger = logging.getLogger(__name__)


class StatefulSetBuilder(BaseModel):
    config: StatefulSetConfig = Field(default_factory=StatefulSetConfig)

    def with_image_in_container(
        self, image: Image, container_name: str, *, overwrite: bool = False
    ) -> Self:
        with_image_for_container(
            config=self.config, image=image, container_name=container_name, overwrite=overwrite
        )
        return self

    def with_replicas(self, replicas: int) -> Self:
        self.config.stateful_set_spec.replicas = replicas
        return self

    def with_label(self, key: str, value: str) -> Self:
        if self.config.labels is None:
            self.config.labels = {}
        self.config.labels[key] = value

        if self.config.stateful_set_spec.selector_labels is None:
            self.config.stateful_set_spec.selector_labels = {}
        self.config.stateful_set_spec.selector_labels[key] = value

        if self.config.stateful_set_spec.pod_template_spec_config.labels is None:
            self.config.stateful_set_spec.pod_template_spec_config.labels = {}
        self.config.stateful_set_spec.pod_template_spec_config.labels[key] = value
        return self

    def with_volume_claim_template(self, pvc: V1PersistentVolumeClaim) -> Self:
        if self.config.volume_claim_templates is None:
            self.config.volume_claim_templates = []
        self.config.volume_claim_templates.append(pvc)
        return self

    def with_network_delay(
        self,
        delay: Union[str, NonNegativeInt],
        jitter: Union[str, NonNegativeInt],
        *,
        overwrite: bool = False,
    ) -> Self:
        delay_container = init_container_delay(delay, jitter)
        self.config.stateful_set_spec.pod_template_spec_config.pod_spec_config.add_init_container(
            delay_container, overwrite=overwrite
        )
        return self

    def with_bandwidth_limit(
        self,
        ingress_rate: Optional[str] = None,
        egress_rate: Optional[str] = None,
        burst: str = "32kbit",
        *,
        overwrite: bool = False,
    ) -> Self:
        """Add bandwidth limit via tc in init container."""
        if not ingress_rate and not egress_rate:
            return self
        bw_container = init_container_bandwidth_limit(
            ingress_rate=ingress_rate,
            egress_rate=egress_rate,
            burst=burst,
        )
        self.config.stateful_set_spec.pod_template_spec_config.pod_spec_config.add_init_container(
            bw_container, overwrite=overwrite
        )
        return self

    def build(self) -> V1StatefulSet:
        if self.config.namespace is None:
            raise ValueError(
                "You must set the namespace before building the StatefulSet. "
                f"config: {self.config}"
            )
        return build_stateful_set(self.config)


class PodBuilder(BaseModel):
    config: PodConfig = Field(default_factory=PodConfig)

    def model_post_init(self, __context) -> None:
        self._register_dependencies()

    @property
    def name(self) -> str | None:
        return self.config.name

    @name.setter
    def name(self, value: str) -> None:
        self.config.name = value
        self._reconcile("name")

    @property
    def namespace(self) -> str | None:
        return self.config.namespace

    @namespace.setter
    def namespace(self, value: str) -> None:
        self.config.namespace = value
        self._reconcile("namespace")

    @property
    def app(self) -> str | None:
        try:
            return self.config.labels["app"]
        except (TypeError, KeyError):
            return None

    @app.setter
    def app(self, value: str) -> None:
        self.config.with_app(value, overwrite=True)
        self._reconcile("app")

    def with_name(self, name: str) -> Self:
        self.name = name
        return self

    def with_namespace(self, namespace: str) -> Self:
        self.namespace = namespace
        return self

    def with_app(self, app: str) -> Self:
        self.app = app
        return self

    def with_image_in_container(
        self, image: Image, container_name: str, *, overwrite: bool = False
    ) -> Self:
        with_image_for_container(
            config=self.config, image=image, container_name=container_name, overwrite=overwrite
        )
        return self

    def _register_dependencies(self) -> None:
        self._dependency_registry = {}
        for cls in type(self).mro():
            for name, maybe_method in cls.__dict__.items():
                fields = getattr(maybe_method, "_depends_on_fields", None)
                if fields:
                    for field in fields:
                        self._dependency_registry.setdefault(field, []).append(name)

    def _reconcile(self, changed_field: Optional[str] = None) -> Self:
        if changed_field is None:
            return self

        for method_name in self._dependency_registry.get(changed_field, []):
            method = getattr(self, method_name)
            required_fields = getattr(method, "_depends_on_fields", set())
            if all(getattr(self, field, None) is not None for field in required_fields):
                method()

        return self

    def build(self) -> V1Pod:
        return build_pod(self.config)


class ServiceBuilder(BaseModel):
    config: ServiceConfig = Field(default_factory=ServiceConfig)

    def with_name(self, name: str) -> Self:
        self.config.name = name
        return self

    def with_namespace(self, namespace: str) -> Self:
        self.config.namespace = namespace
        return self

    def with_cluster_ip(self, cluster_ip: str) -> Self:
        self.config.service_spec.cluster_ip = cluster_ip
        return self

    def with_selector(self, key: str, value: str) -> Self:
        self.config.service_spec.with_selector(key, value)
        return self

    def with_port(self, new_port: V1ServicePort) -> Self:
        self.config.service_spec.with_port(new_port)
        return self

    def with_type(self, spec_type: ServiceSpecType) -> Self:
        self.config.service_spec.spec_type = spec_type
        return self

    def with_publish_not_ready_addresses(self, value: bool = True) -> Self:
        """Set publishNotReadyAddresses for headless services."""
        self.config.service_spec.publish_not_ready_addresses = value
        return self

    def build(self) -> V1Service:
        return build_service(self.config)


class ContainerBuilder:
    config: ContainerConfig

    def __init__(self, config: Optional[ContainerConfig] = None):
        if config is None:
            config = ContainerConfig()
        self.config = config

    def build(self) -> V1Container:
        return build_container(self.config)

    def with_command_script(self, script: List[str]) -> Self:
        """
        Copy-paste entire script as string into the `command` field of the container.

        The script will be appended to any existing commands in the container.
        """
        for line in script:
            self.config.command_config.insert_command(command=line, args=[], multiline=False)
        return self

    def with_readiness_probe(self, probe: V1Probe) -> Self:
        self.config.with_readiness_probe(probe)
        return self

    def with_resources(self, resources: V1ResourceRequirements) -> Self:
        self.config.with_resources(resources)
        return self


class PodTemplateSpecBuilder(BaseModel):
    config: PodTemplateSpecConfig = Field(default_factory=PodTemplateSpecConfig)

    def build(self) -> V1PodTemplateSpec:
        return build_pod_template_spec(self.config)


class PodSpecBuilder(BaseModel):
    config: PodSpecConfig = Field(default_factory=PodSpecConfig)

    def build(self) -> V1PodSpec:
        return build_pod_spec(self.config)

    def add_container(self, container: ContainerConfig | V1Container | dict):
        self.config.add_container(container)
        return self

    def add_init_container(self, init_container: ContainerConfig | V1Container | dict):
        self.config.add_init_container(init_container)
        return self

    def with_service_account_name(self, name: str, *, overwrite: bool = False) -> Self:
        self.config.with_service_account_name(name, overwrite=overwrite)
        return self


class ContainerCommandBuilder(BaseModel):
    config: CommandConfig = Field(default_factory=CommandConfig)

    def build(self) -> List[str]:
        return build_command(self.config)

    def add_line(
        self,
        command: str,
        args: None | List[str | Tuple[str, Optional[str]]],
        *,
        multiline: bool = False,
    ) -> Self:
        if args is None:
            args = []
        self.config.commands.append(Command(command=command, args=args, multiline=multiline))
        return self


def default_readiness_probe_health() -> dict:
    return {
        "failureThreshold": 1,
        "httpGet": {
            "path": "/health",
            "port": 8008,
        },
        "initialDelaySeconds": 1,
        "periodSeconds": 3,
        "successThreshold": 3,
        "timeoutSeconds": 5,
    }
