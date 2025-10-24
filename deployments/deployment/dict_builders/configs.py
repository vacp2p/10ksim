import json
from copy import deepcopy
from typing import Dict, List, Literal, Optional

from kubernetes import client
from kubernetes.client import (
    V1Container,
    V1ContainerPort,
    V1EnvVar,
    V1PersistentVolumeClaim,
    V1PodDNSConfig,
    V1Probe,
    V1ResourceRequirements,
    V1Volume,
    V1VolumeMount,
)
from pydantic import BaseModel, ConfigDict

from deployment.dict_builders.waku import CommandConfig


class Image(BaseModel):
    repo: str
    tag: str

    @staticmethod
    def from_str(image: str):
        repo, tag = image.split(":")
        return Image(repo=repo, tag=tag)

    def __str__(self):
        return f"{self.repo}:{self.tag}"


class ContainerConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    command_config: CommandConfig = CommandConfig()
    readiness_probe: Optional[V1Probe] = None
    volume_mounts: Optional[List[V1VolumeMount]] = None
    resources: Optional[V1ResourceRequirements] = None
    env: List[V1EnvVar] = []
    name: str
    image: Optional[Image] = None
    ports: Optional[List[V1ContainerPort]] = None
    image_pull_policy: Literal["IfNotPresent", "Always", "Never"]

    def with_resources(self, resources: V1ResourceRequirements, *, overwrite=False):
        if self.resources is not None and not overwrite:
            raise ValueError("Resources already exist for container")
        self.resources = resources

    def with_env_var(self, var: V1EnvVar, allow_duplicates=False):
        if any([item.name == var.name for item in self.env]):
            raise ValueError(f"Attempt to add duplicate environment variable: `{var}`")
        self.env.append(var)

    def with_readines_probe(self, readiness_probe: V1Probe, overwrite=False):
        if self.readiness_probe is not None and overwrite == False:
            raise ValueError("ContainerConfig already has readiness probe.")
        self.readiness_probe = readiness_probe


def v1container_to_container_config(v1container: V1Container) -> ContainerConfig:
    command_config = CommandConfig()
    if v1container.command is not None:
        command_config.with_command(
            command=" ".join(deepcopy(v1container.command)),
            args=deepcopy(v1container.args) if v1container.args else [],
            multiline=False,
        )

    container_config = ContainerConfig(
        name=v1container.name,
        image=Image.from_str(v1container.image) if v1container.image else None,
        ports=deepcopy(v1container.ports or []),
        env=deepcopy(v1container.env or []),
        volume_mounts=deepcopy(v1container.volume_mounts),
        readiness_probe=deepcopy(v1container.readiness_probe),
        image_pull_policy=v1container.image_pull_policy,
        resources=deepcopy(v1container.resources),
        command_config=command_config,
    )
    return container_config


K8sModelStr = Literal[
    "V1Pod",
    "V1PodSpec",
    "V1Container",
    "V1Service",
    "V1Deployment",
    "V1StatefulSet",
    "V1DaemonSet",
    "V1Job",
    "V1ConfigMap",
    "V1Secret",
    "V1PersistentVolumeClaim",
    "V1Ingress",
    "V1ResourceRequirements",
    "V1Volume",
    "V1EnvVar",
    "V1Probe",
]


def dict_to_k8s_object(data: dict, model: K8sModelStr):
    """Convert a Kubernetes-style dict to a typed client model."""
    api_client = client.ApiClient()

    class _FakeResponse:
        def __init__(self, obj):
            self.data = json.dumps(obj)

    return api_client.deserialize(_FakeResponse(data), model)


def dict_to_container_config(container_dict: dict) -> ContainerConfig:
    v1container = dict_to_k8s_object(container_dict, "V1Container")
    return v1container_to_container_config(v1container)


def convert_to_container_config(container: ContainerConfig | V1Container | dict) -> ContainerConfig:
    if isinstance(container, ContainerConfig):
        container_config = container
    elif isinstance(container, V1Container):
        container_config = v1container_to_container_config(container)
    elif isinstance(container, dict):
        container_config = dict_to_container_config(container)
    else:
        raise TypeError("Unsupported container type")
    return container_config


class PodSpecConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    volumes: List[V1Volume] = []
    init_containers: Optional[List[ContainerConfig]] = None
    container_configs: List[ContainerConfig] = []
    dns_config: Optional[V1PodDNSConfig] = None

    def add_init_container(self, init_container: ContainerConfig | V1Container | dict):
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


class StatefulSetSpecConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    replicas: Optional[int] = 1
    selector_labels: Optional[Dict[str, str]] = None
    service_name: Optional[str] = None
    pod_template_spec_config: PodTemplateSpecConfig = PodTemplateSpecConfig()
    volume_claim_templates: Optional[List[V1PersistentVolumeClaim]] = None

    def with_app(self, app: str):
        if self.selector_labels is None:
            self.selector_labels = {}
        self.selector_labels["app"] = app


class StatefulSetConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: Optional[str] = None
    namespace: Optional[str] = None
    apiVersion: Optional[str] = None
    kind: Optional[str] = None
    labels: Optional[Dict[str, str]] = None
    stateful_set_spec: StatefulSetSpecConfig = StatefulSetSpecConfig()
    pod_management_policy: Optional[Literal["Parallel", "OrderedReady"]] = None
