# Python Imports
from pathlib import Path
from typing import List, Literal, Optional, Self

import yaml
from kubernetes.client import (
    V1ConfigMap,
    V1ConfigMapVolumeSource,
    V1ContainerPort,
    V1ObjectMeta,
    V1Pod,
    V1PodDNSConfig,
    V1PolicyRule,
    V1ResourceRequirements,
    V1Role,
    V1RoleBinding,
    V1RoleRef,
    V1Service,
    V1ServicePort,
    V1ServiceSpec,
    V1Volume,
    V1VolumeMount,
)

# Project Imports
from src.deployments.core.builders import PodBuilder, ServiceBuilder
from src.deployments.core.configs.command import Command, CommandConfig
from src.deployments.core.configs.container import ContainerConfig, Image
from src.deployments.core.configs.helpers.utils import find_container_config
from src.deployments.core.configs.pod import PodConfig, PodSpecConfig, PodTemplateSpecConfig

ScriptMode = Literal["server", "batch"]


NAME = "pod-api-requester-container"
PUBLISHER_SERVICE_NAME = "zerotesting-publisher"
PUBLISHER_APP = "zerotenkay-publisher"
CONFIGMAP_NAME = "api-requester-config"
NODE_SERVICE_NAME = "nimp2p-service"


class PodApiRequesterBuilder(PodBuilder):
    _mode: Optional[ScriptMode] = None
    """Sent to the --mode arg of the api-requester script.
    This must be set through `with_mode` prior to building."""

    _restart_policy: Optional[Literal["Always", "OnFailure", "Never"]] = None
    """Restart policy for the pod (for batch mode)."""

    def build_role(self) -> V1Role:
        return V1Role(
            api_version="rbac.authorization.k8s.io/v1",
            kind="Role",
            metadata=V1ObjectMeta(
                name="pod-service-reader",
                namespace=self.config.namespace,
            ),
            rules=[
                V1PolicyRule(
                    api_groups=[""], resources=["pods", "services"], verbs=["get", "list", "watch"]
                )
            ],
        )

    def build_rolebinding(self) -> V1RoleBinding:
        return V1RoleBinding(
            api_version="rbac.authorization.k8s.io/v1",
            kind="RoleBinding",
            metadata=V1ObjectMeta(
                name="pod-service-reader-binding", namespace=self.config.namespace
            ),
            role_ref=V1RoleRef(
                kind="Role",
                name="pod-service-reader",
                api_group="rbac.authorization.k8s.io",
            ),
            subjects=[
                {
                    "kind": "ServiceAccount",
                    "name": "default",
                    "namespace": self.config.namespace,
                },
            ],
        )

    def build(self) -> V1Pod:
        if not self.config.name:
            raise ValueError(f"Must configure node first. Config: `{self.config}`")
        if not self._mode:
            raise ValueError(
                f"Script mode must be set using `with_mode` before building. Config: `{self.config}`"
            )

        pod = super().build()

        # Apply restart policy if set, or auto-set for batch mode
        if self._restart_policy:
            pod.spec.restart_policy = self._restart_policy
        elif self._mode == "batch":
            # Batch mode should not restart on completion
            pod.spec.restart_policy = "Never"

        return pod

    def with_image_override(self, image: Image) -> Self:
        """Allow overriding the default publisher image."""
        container = find_container_config(self.config.pod_spec_config, NAME)
        container.with_image(image, overwrite=True)
        return self

    def with_restart_policy(self, policy: Literal["Always", "OnFailure", "Never"]) -> Self:
        """Set pod restart policy (for batch mode, use 'Never')."""
        self._restart_policy = policy
        return self

    def with_name(self, name: str) -> Self:
        """Set pod name."""
        self.config.name = name
        return self

    def with_config_map(self, configmap_name: str) -> Self:
        """Set the ConfigMap name for the api-requester config."""
        for volume in self.config.pod_spec_config.volumes:
            if volume.name == "api-requester-config-volume":
                volume.config_map = V1ConfigMapVolumeSource(name=configmap_name)
                break
        return self

    def with_namespace(self, namespace: str) -> Self:
        self.config = create_pod_config(namespace=namespace)
        return self

    def with_mode(self, mode: ScriptMode) -> Self:
        container = find_container_config(self.config.pod_spec_config, NAME)
        apply_command_config(container.command_config, mode=mode)
        self._mode = mode
        return self

    def with_command(self, command: str, args: List[str]) -> Self:
        container_config = find_container_config(self.config.pod_spec_config, NAME)
        container_config.command_config = CommandConfig(
            commands=[Command(command=command, args=args)]
        )
        return self

    def with_debug(self) -> Self:
        self._mode = "debug"
        return self.with_command("sleep", args=["infinity"])


def apply_command_config(config: CommandConfig, mode: ScriptMode = "server"):
    try:
        command = config.find_command("python")
    except IndexError as e:
        raise ValueError(f"pod-api-requester command not found. CommandConfig: `{config}`") from e

    command.add_args(
        [
            ("--mode", mode),
            ("--config", "/mount/config.yaml"),
        ],
        on_duplicate="replace",
    )


def create_container_config() -> ContainerConfig:
    config = ContainerConfig(
        name=NAME,
        image=Image(
            repo="pearsonwhite/pod-api-requester", tag="10b85bb60895fe63aa8d3f09b24b714f2abce300"
        ),
        image_pull_policy="Always",
    )
    config.ports = [
        V1ContainerPort(8645),
        V1ContainerPort(8008),
        V1ContainerPort(8080),
    ]

    config.with_volume_mount(V1VolumeMount(name="api-requester-config-volume", mount_path="/mount"))
    config.command_config = CommandConfig(
        commands=[Command(command="python", args=["/app/api_requester.py"])]
    )

    return config


def create_pod_spec_config(namespace: str) -> PodSpecConfig:
    config = PodSpecConfig(
        container_configs=[create_container_config()],
        dns_config=V1PodDNSConfig(
            searches=[f"zerotesting-publisher.{namespace}.svc.cluster.local"]
        ),
        namespace=namespace,
    )
    config.with_volume(
        V1Volume(
            name="api-requester-config-volume",
            config_map=V1ConfigMapVolumeSource(name="api-requester-config"),
        )
    )
    return config


def create_pod_template_spec_config(namespace: str) -> PodTemplateSpecConfig:
    config = PodTemplateSpecConfig(
        pod_spec_config=create_pod_spec_config(namespace),
        namespace=namespace,
        name="publisher",
    )
    config.with_app("zerotenkay-publisher")
    return config


def create_pod_config(namespace: str) -> PodConfig:
    config = PodConfig(
        name="publisher",
        namespace=namespace,
        pod_spec_config=create_pod_spec_config(namespace=namespace),
    )
    config.with_app("zerotenkay-publisher")
    return config


def create_resources() -> V1ResourceRequirements:
    return V1ResourceRequirements(
        requests={"memory": "64Mi", "cpu": "150m"}, limits={"memory": "600Mi", "cpu": "400m"}
    )


def build_node_governance_service(namespace: str) -> V1Service:
    """Headless service the node StatefulSets require: spec.serviceName is hardcoded to
    NODE_SERVICE_NAME, so pods only get stable per-pod DNS through it."""
    return (
        ServiceBuilder()
        .with_name(NODE_SERVICE_NAME)
        .with_namespace(namespace)
        .with_cluster_ip("None")
        .with_selector("app", "zerotenkay")
        .with_port(V1ServicePort(name="p2p", port=5000, target_port=5000))
        .build()
    )


def build_publisher_service(namespace: str) -> V1Service:
    """NodePort service the 10ksim driver reaches the publisher pod through."""
    return V1Service(
        api_version="v1",
        kind="Service",
        metadata=V1ObjectMeta(name=PUBLISHER_SERVICE_NAME, namespace=namespace),
        spec=V1ServiceSpec(
            type="NodePort",
            selector={"app": PUBLISHER_APP},
            ports=[
                V1ServicePort(
                    name="http", protocol="TCP", port=8000, target_port=8645, node_port=30080
                )
            ],
        ),
    )


def build_api_requester_configmap(namespace: str) -> V1ConfigMap:
    """ConfigMap mounted into the publisher pod; reuses the checked-in config.yaml so the
    api-requester script has a valid config to load (targets are passed per-request)."""
    template = yaml.safe_load((Path(__file__).parent / "config.yaml").read_text())
    return V1ConfigMap(
        api_version="v1",
        kind="ConfigMap",
        metadata=V1ObjectMeta(name=CONFIGMAP_NAME, namespace=namespace),
        data=template["data"],
    )
