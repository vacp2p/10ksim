from typing import List, Literal, Optional, Self

from kubernetes.client import (
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
    V1Subject,
    V1Volume,
    V1VolumeMount,
)

from core.builders import (
    PodBuilder,
)
from core.configs.command import Command, CommandConfig
from core.configs.container import ContainerConfig, Image
from core.configs.helpers import find_container_config
from core.configs.pod import PodConfig, PodSpecConfig, PodTemplateSpecConfig

ScriptMode = Literal["server", "batch"]


NAME = "pod-api-requester-container"


class PodApiRequesterBuilder(PodBuilder):
    _mode: Optional[ScriptMode] = None
    """Sent to the --mode arg of the api-requester script.
    This must be set through `with_mode` prior to building."""

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
                apiGroup="rbac.authorization.k8s.io",
            ),
            subjects=[
                V1Subject(
                    kind="ServiceAccount",
                    name="default",
                    namespace=self.config.namespace,
                ),
            ],
        )

    def build(self) -> V1Pod:
        if not self.config.name:
            raise ValueError(f"Must configure node first. Config: `{self.config}`")
        if not self._mode:
            raise ValueError(
                f"Script mode must be set using `with_mode` before building. Config: `{self.config}`"
            )
        return super().build()

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
            repo="pearsonwhite/pod-api-requester", tag="4575c70fd1efddabb7673ebe8a1f2b482473e0db"
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
