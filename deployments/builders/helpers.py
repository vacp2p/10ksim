import json
from copy import deepcopy
from typing import Literal

from kubernetes import client
from kubernetes.client import (
    V1Container,
)

from builders.configs import (
    CommandConfig,
    ContainerConfig,
    Image,
)


def v1container_to_container_config(v1container: V1Container) -> ContainerConfig:
    command_config = CommandConfig(single_k8s_command=False)
    if v1container.args:
        command_config.use_single_command(True)
    if v1container.command is not None:
        command_config.with_command(
            command=" ".join(deepcopy(v1container.command)),
            args=deepcopy(v1container.args) if v1container.args else [],
            multiline=False,
        )

    container_config = ContainerConfig(
        name=v1container.name,
        image=Image.from_str(v1container.image) if v1container.image else None,
        ports=deepcopy(v1container.ports),
        env=deepcopy(v1container.env),
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
    """Convert a dict to a Kubernetes object."""
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
