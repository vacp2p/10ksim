# Python Imports
from copy import deepcopy
from typing import Dict, List, Literal, Optional, Tuple, Type, TypeVar, get_args

from kubernetes.client import V1Capabilities, V1Container, V1SecurityContext
from pydantic import NonNegativeInt

# Project Imports
from src.deployments.core.configs.command import CommandConfig
from src.deployments.core.configs.container import ContainerConfig, Image
from src.deployments.core.configs.pod import PodConfig, PodSpecConfig, PodTemplateSpecConfig
from src.deployments.core.configs.statefulset import StatefulSetConfig, StatefulSetSpecConfig
from src.deployments.core.k8s_object import dict_to_k8s_object

T = TypeVar("T")
_sentinel = object()


class ContainerNotFoundError(ValueError):
    pass


HigherConfigTypes = (
    StatefulSetConfig | StatefulSetSpecConfig | PodConfig | PodTemplateSpecConfig | PodSpecConfig
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
        if isinstance(config, PodConfig):
            config = config.pod_spec_config
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


def with_image_for_container(
    config: StatefulSetSpecConfig | StatefulSetConfig | PodTemplateSpecConfig | PodConfig,
    image: Image,
    container_name: str,
    *,
    overwrite: bool = False,
):
    container_config = find_container_config(config, container_name)
    container_config.with_image(image, overwrite=overwrite)


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
        security_context=v1container.security_context,
        ports=deepcopy(v1container.ports),
        env=deepcopy(v1container.env),
        volume_mounts=deepcopy(v1container.volume_mounts),
        readiness_probe=deepcopy(v1container.readiness_probe),
        image_pull_policy=v1container.image_pull_policy,
        resources=deepcopy(v1container.resources),
        command_config=command_config,
    )
    return container_config


def dict_to_container_config(container_dict: dict) -> ContainerConfig:
    v1container = dict_to_k8s_object(container_dict, "V1Container")
    return v1container_to_container_config(v1container)


def convert_to_container_config(
    container: ContainerConfig | V1Container | dict,
) -> ContainerConfig:
    if isinstance(container, ContainerConfig):
        container_config = container
    elif isinstance(container, V1Container):
        container_config = v1container_to_container_config(container)
    elif isinstance(container, dict):
        container_config = dict_to_container_config(container)
    else:
        raise TypeError("Unsupported container type")
    return container_config


def init_container_delay(
    delay: NonNegativeInt,
    jitter: NonNegativeInt,
    rate_mbit: Optional[NonNegativeInt] = None,
):
    netem = f"delay {delay}ms"
    if jitter:
        netem += f" {jitter}ms distribution normal"
    if rate_mbit:
        netem += f" rate {rate_mbit}mbit"
    return V1Container(
        name="slowyourroll",
        image="soutullostatus/tc-container:1",
        image_pull_policy="IfNotPresent",
        security_context=V1SecurityContext(capabilities=V1Capabilities(add=["NET_ADMIN"])),
        command=[f"tc qdisc add dev eth0 root netem {netem}"],
    )


def init_container_bandwidth_limit(
    ingress_rate: Optional[str] = None,
    egress_rate: Optional[str] = None,
    burst: str = "32kbit",
    latency: str = "400ms",
) -> V1Container:
    """
    Create init container for limiting bandwidth using tc with TBF (Token Bucket Filter).

    For ingress limiting, uses IFB device for proper queuing/buffering instead of policing.
    Requires IFB module loaded on host (modprobe ifb).

    Args:
        ingress_rate: Download limit (e.g., "512kbit", "1mbit")
        egress_rate: Upload limit (e.g., "512kbit", "1mbit")
        burst: Token bucket burst size
        latency: Maximum queuing delay (determines queue depth with rate)

    Returns:
        V1Container configured to set up tc bandwidth limits with proper buffering
    """
    commands = []

    if ingress_rate:
        # Ingress limiting with IFB for proper queuing/buffering
        commands.extend(
            [
                "ip link add ifb0 type ifb",
                "ip link set ifb0 up",
                "tc qdisc add dev eth0 handle ffff: ingress",
                "tc filter add dev eth0 parent ffff: protocol all u32 match u32 0 0 action mirred egress redirect dev ifb0",
                f"tc qdisc add dev ifb0 root tbf rate {ingress_rate} burst {burst} latency {latency}",
            ]
        )

    if egress_rate:
        # Egress limiting with TBF
        commands.append(
            f"tc qdisc add dev eth0 root tbf rate {egress_rate} burst {burst} latency {latency}"
        )

    full_command = " && ".join(commands)

    return V1Container(
        name="setup-bandwidth-limit",
        image="soutullostatus/tc-container:1",
        image_pull_policy="IfNotPresent",
        security_context=V1SecurityContext(
            privileged=True,  # Required to create virtual network devices
            capabilities=V1Capabilities(add=["NET_ADMIN"]),
        ),
        command=[full_command],
    )
