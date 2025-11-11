from copy import deepcopy
from typing import List, Optional, Tuple

from kubernetes.client import (
    V1Container,
    V1LabelSelector,
    V1ObjectMeta,
    V1PodSpec,
    V1PodTemplateSpec,
    V1StatefulSet,
    V1StatefulSetSpec,
)

from builders.configs.command import CommandConfig
from builders.configs.container import ContainerConfig
from builders.configs.pod import PodSpecConfig, PodTemplateSpecConfig
from builders.configs.statefulset import StatefulSetConfig


def build_command(config: CommandConfig) -> Tuple[Optional[List[str]], Optional[List[str]]]:
    """
    If there are no commands, returns (None, None).

    If config.single_k8s_command is True, then returns `(command : List[str], args : List[str])`

    Otherwise returns a script command with all commands and arguments with None for args: `(command : List[str], None)`

    :rtype: Tuple[Optional[List[str]], Optional[List[str]]]
    :returns: (command, args)
    """
    if not config.commands:
        return None, None
    if config.single_k8s_command:
        if len(config.commands) != 1:
            raise ValueError(
                f"Attempt to build single Kubernetes command with multiple commands. config: `{config}`"
            )
        return [config.commands[0].command], deepcopy(config.commands[0].args)

    command_lines = []
    for command in config.commands:
        command_lines.append(str(command))
    command = build_container_command(command_lines)
    return command, None


def build_container_command(
    command_lines: List[str], prefix: Optional[List[str]] = None
) -> List[str]:
    if prefix is None:
        prefix = ["sh", "-c"]
    # The newline is added to the end of command to prevent chomp in dumped yaml.
    # We want `|` not `|-` in the final output.
    return prefix + ["\n".join(command_lines) + "\n"]


def build_container(config: ContainerConfig) -> V1Container:
    command, args = build_command(config.command_config)
    return V1Container(
        name=config.name,
        image=str(config.image),
        image_pull_policy=config.image_pull_policy,
        ports=deepcopy(config.ports),
        env=deepcopy(config.env),
        resources=deepcopy(config.resources),
        readiness_probe=deepcopy(config.readiness_probe),
        volume_mounts=deepcopy(config.volume_mounts),
        command=command,
        args=args,
    )


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


def build_stateful_set(config: StatefulSetConfig) -> V1StatefulSet:
    return V1StatefulSet(
        api_version=config.apiVersion,
        kind=config.kind,
        metadata=V1ObjectMeta(name=config.name, namespace=config.namespace, labels=config.labels),
        spec=V1StatefulSetSpec(
            replicas=config.stateful_set_spec.replicas,
            pod_management_policy=config.pod_management_policy,
            selector=V1LabelSelector(match_labels=config.stateful_set_spec.selector_labels),
            service_name=config.stateful_set_spec.service_name,
            template=build_pod_template_spec(config.stateful_set_spec.pod_template_spec_config),
            volume_claim_templates=config.stateful_set_spec.volume_claim_templates,
        ),
    )
