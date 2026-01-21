from typing import List, Optional, Self, Tuple

from kubernetes.client import (
    V1Container,
    V1PersistentVolumeClaim,
    V1Pod,
    V1PodSpec,
    V1PodTemplateSpec,
    V1Probe,
    V1ResourceRequirements,
    V1StatefulSet,
)
from pydantic import BaseModel, Field

from core.configs.command import (
    Command,
    CommandConfig,
    build_command,
)
from core.configs.container import (
    ContainerConfig,
    build_container,
)
from core.configs.pod import (
    PodConfig,
    PodSpecConfig,
    PodTemplateSpecConfig,
    build_pod,
    build_pod_spec,
    build_pod_template_spec,
)
from core.configs.statefulset import (
    StatefulSetConfig,
    build_stateful_set,
)


class StatefulSetBuilder(BaseModel):
    config: StatefulSetConfig = Field(default_factory=StatefulSetConfig)

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


class PodBuilder(BaseModel):
    config: PodConfig = Field(default_factory=PodConfig)

    def with_app(self, app: str, *, overwrite: bool = False) -> Self:
        self.config.with_app(app, overwrite=overwrite)
        return self

    def build(self) -> V1Pod:
        return build_pod(self.config)


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


class PodSpecBuilder:
    config: PodSpecConfig = Field(default_factory=PodSpecConfig)

    def build(self) -> V1PodSpec:
        return build_pod_spec(self.config)

    def add_container(self, container: ContainerConfig | V1Container | dict):
        self.config.add_container(container)
        return self

    def add_init_container(self, init_container: ContainerConfig | V1Container | dict):
        self.config.add_init_container(init_container)
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
