import json
from copy import deepcopy
from typing import Dict, List, Literal, Tuple, Type, TypeVar, get_args

from kubernetes import client
from kubernetes.client import V1Container, V1Probe

from core.configs.command import CommandConfig
from core.configs.container import ContainerConfig, Image
from core.configs.pod import PodSpecConfig, PodTemplateSpecConfig
from core.configs.statefulset import StatefulSetConfig, StatefulSetSpecConfig

T = TypeVar("T")
_sentinel = object()


class ContainerNotFoundError(ValueError):
    pass


HigherConfigTypes = (
    StatefulSetConfig | StatefulSetSpecConfig | PodTemplateSpecConfig | PodSpecConfig
)


def get_config(config: HigherConfigTypes, target: Type[T]) -> T:
    source_type = type(config)
    if target not in get_args(HigherConfigTypes):
        raise ValueError(
            f"Unsupported target type. Config type: `{source_type}` Target type: `{target}`"
        )
    if not isinstance(config, HigherConfigTypes):
        raise ValueError(
            f"Unsupported config type. Config type: `{source_type}` Target type: `{target}`"
        )

    class ConversionDone(Exception):
        pass

    def check_done():
        if isinstance(config, target):
            raise ConversionDone()

    try:
        check_done()
        if isinstance(config, StatefulSetConfig):
            config = config.stateful_set_spec
        check_done()
        if isinstance(config, StatefulSetSpecConfig):
            config = config.pod_template_spec_config
        check_done()
        if isinstance(config, PodTemplateSpecConfig):
            config = config.pod_spec_config
        check_done()
        raise TypeError(
            f"Unsupported config conversion. "
            f"Config type: `{source_type}` "
            f"Target type: `{target}`"
        )
    except ConversionDone:
        return config


def find_container_config(
    config: HigherConfigTypes, name: str, *, default: T | object = _sentinel
) -> ContainerConfig | T:
    """Finds the ContainerConfig with a given name from a PodSpecConfig"""
    config = get_config(config, PodSpecConfig)
    result = next((item for item in config.container_configs if item.name == name), default)
    if result is _sentinel:
        raise ContainerNotFoundError(
            f"Failed to find container in config. name: `{name}` config: `{config}`"
        )
    return result


def get_container_command(
    config: HigherConfigTypes,
    container_name: str,
    command_name: str,
):
    """Find command in command_config for container with given name."""

    container_config = find_container_config(config, container_name)
    return container_config.command_config.find_command(command_name)


def with_container_command_args(
    config: StatefulSetSpecConfig | StatefulSetConfig | PodTemplateSpecConfig,
    container_name: str,
    command_name: str,
    args: List[str | Tuple[str, str]] | Dict[str, str],
    *,
    on_duplicate: Literal["error", "ignore", "replace"] = "error",
):
    """
    Modifies command args for a named container inside the config.
    """
    command = get_container_command(config, container_name, command_name)
    command.add_args(args, on_duplicate=on_duplicate)


def v1container_to_container_config(v1container: V1Container) -> ContainerConfig:
    command_config = CommandConfig(single_k8s_command=False)
    if v1container.args:
        command_config.use_single_command(True)
    if v1container.command is not None:
        command_config.insert_command(
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


def dict_to_v1probe(probe_dict: dict) -> V1Probe:
    return dict_to_k8s_object(probe_dict, "V1Probe")


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
