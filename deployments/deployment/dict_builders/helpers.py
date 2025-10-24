from typing import Dict, List, Tuple, TypeVar

from kubernetes.client import V1ExecAction, V1Probe

from deployment.dict_builders.configs import (
    ContainerConfig,
    PodSpecConfig,
    PodTemplateSpecConfig,
    StatefulSetConfig,
    StatefulSetSpecConfig,
)
from deployment.dict_builders.waku import Command, CommandConfig, readiness_probe_command_metrics

# TODO: rename everything apply_ or create_


WAKU_COMMAND_STR = "/usr/bin/wakunode"

# ---- helpers ----


# TODO: add _sentinel and CommandNotFoundError
def find_command(config: CommandConfig, command_name: str) -> Command | None:
    """Finds the Command for the given command in the ContainerConfig"""
    return next(
        (command for command in config.commands if command.command == command_name),
        None,
    )


def find_waku_command(config: CommandConfig) -> Command | None:
    return find_command(config, WAKU_COMMAND_STR)


class ContainerNotFoundError(ValueError):
    pass


T = TypeVar("T")
_sentinel = object()


def find_container_config(
    config: PodSpecConfig, name: str, *, default: T | object = _sentinel
) -> ContainerConfig | T:
    """Finds the ContainerConfig for Waku from a PodSpecConfig"""
    result = next((item for item in config.container_configs if item.name == name), default)
    if result is _sentinel:
        raise ContainerNotFoundError(
            f"Failed to find container in config. name: `{name}` config: `{config}`"
        )
    return result


def find_waku_container_config(config: PodSpecConfig) -> ContainerConfig | None:
    """Finds the ContainerConfig for Waku from a PodSpecConfig"""
    return find_container_config(config, "waku")


def extend_container_command_args(
    config: StatefulSetSpecConfig | StatefulSetConfig | PodTemplateSpecConfig,
    container_name: str,
    command_name: str,
    args: List[str | Tuple[str, str]] | Dict[str, str],
):
    """
    Modifies command args for a named container inside the config.
    """
    if isinstance(config, StatefulSetConfig):
        config = config.stateful_set_spec
    if isinstance(config, StatefulSetSpecConfig):
        config = config.pod_template_spec_config
    if isinstance(config, PodTemplateSpecConfig):
        config = config.pod_spec_config
    if not isinstance(config, PodSpecConfig):
        raise TypeError(f"Unsupported config type: {type(config)}")

    container_config = find_container_config(config, container_name)
    command = find_command(container_config.command_config, command_name)
    command.add_args(args)


def readiness_probe_metrics():
    return V1Probe(
        _exec=V1ExecAction(command=readiness_probe_command_metrics()),
        success_threshold=5,
        initial_delay_seconds=5,
        period_seconds=1,
        failure_threshold=2,
        timeout_seconds=5,
    )


def readiness_probe_health() -> V1Probe:
    config = {
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
    return V1Probe(**config)
