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
from pydantic import PrivateAttr

# Project Imports
from src.deployments.core.builders import PodBuilder
from src.deployments.core.configs.command import Command, CommandConfig, CommandNotFoundError
from src.deployments.core.configs.container import ContainerConfig, Image
from src.deployments.core.configs.helpers.identity import apply_identity
from src.deployments.core.configs.helpers.utils import find_container_config, get_config
from src.deployments.core.configs.pod import PodConfig, PodSpecConfig
from src.deployments.core.k8s_object import dict_to_k8s_object

ScriptMode = Literal["server", "batch"]


class PodApiRequesterBuilder(PodBuilder):
    _mode: Optional[ScriptMode] = None
    """Sent to the --mode arg of the api-requester script.
    This must be set through `with_mode` prior to building."""

    _restart_policy: Optional[Literal["Always", "OnFailure", "Never"]] = None
    """Restart policy for the pod (for batch mode)."""

    _container_name: str = PrivateAttr(default="pod-api-requester-container")
    _namespace: Optional[str] = PrivateAttr(default=None)
    _name: Optional[str] = PrivateAttr(default=None)
    _app: Optional[str] = PrivateAttr(default=None)
    _pod_service_reader_role_name: str = PrivateAttr(default="pod-service-reader")
    _pod_service_reader_binding_name: str = PrivateAttr(default="pod-service-reader-binding")
    _image: Image = PrivateAttr(
        default_factory=lambda: Image(
            repo="pearsonwhite/pod-api-requester", tag="10b85bb60895fe63aa8d3f09b24b714f2abce300"
        )
    )

    def _ensure_container(self):
        container_config = find_container_config(self.config, self._container_name, default=None)
        if not container_config:
            pod_config = get_config(self.config, PodSpecConfig)
            pod_config.add_container(
                ContainerConfig(name=self._container_name, image_pull_policy="IfNotPresent")
            )

    def with_container_name(self, container_name: str) -> Self:
        self._ensure_container()
        container_config = find_container_config(self.config, self._container_name)
        self._container_name = container_name
        container_config.name = self._container_name
        return self

    def with_image(self, image: Image) -> Self:
        self._ensure_container()
        self._image = image
        apply_pod_config(
            namespace=self._namespace,
            container_name=self._container_name,
            image=self._image,
            config=self.config,
        )
        return self

    def build_role(self) -> V1Role:
        return V1Role(
            api_version="rbac.authorization.k8s.io/v1",
            kind="Role",
            metadata=V1ObjectMeta(
                name=self._pod_service_reader_role_name,
                namespace=self.config.namespace,
            ),
            rules=[
                V1PolicyRule(
                    api_groups=[""],
                    resources=["pods", "services"],
                    verbs=["get", "list", "watch"],
                )
            ],
        )

    def build_rolebinding(self) -> V1RoleBinding:
        return V1RoleBinding(
            api_version="rbac.authorization.k8s.io/v1",
            kind="RoleBinding",
            metadata=V1ObjectMeta(
                name=self._pod_service_reader_binding_name,
                namespace=self.config.namespace,
            ),
            role_ref=V1RoleRef(
                kind="Role",
                name=self._pod_service_reader_role_name,
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

    def build_config_map(self) -> V1ConfigMap:
        with open(Path(__file__).parent / "config.yaml", "r") as config_file:
            config_dict = yaml.safe_load(config_file.read())
        config_map: V1ConfigMap = dict_to_k8s_object(config_dict, "V1ConfigMap")
        config_map.metadata.namespace = self.config.namespace
        return config_map

    def build_service(self) -> V1Service:
        return V1Service(
            api_version="v1",
            kind="Service",
            metadata=V1ObjectMeta(name="zerotesting-publisher", namespace=self.config.namespace),
            spec=V1ServiceSpec(
                type="NodePort",
                selector={"app": "zerotenkay-publisher"},
                ports=[
                    V1ServicePort(
                        protocol="TCP",
                        port=8000,
                        target_port=8645,
                    )
                ],
            ),
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
        self._namespace = namespace
        apply_identity(self.config, name=self._name, namespace=self._namespace, app=self._app)
        self._ensure_container()
        apply_pod_config(
            namespace=namespace,
            container_name=self._container_name,
            image=self._image,
            config=self.config,
        )
        return self

    def with_mode(self, mode: ScriptMode) -> Self:
        self._ensure_container()
        container = find_container_config(self.config.pod_spec_config, self._container_name)
        apply_command_config(container.command_config, mode=mode)
        self._mode = mode
        return self

    def with_command(self, command: str, args: List[str]) -> Self:
        container_config = find_container_config(self.config.pod_spec_config, self._container_name)
        container_config.command_config = CommandConfig(
            commands=[Command(command=command, args=args)]
        )
        return self

    def with_dns_search(self, search) -> Self:
        self.config.pod_spec_config.with_dns_service(search)
        return self

    def with_debug(self) -> Self:
        self._mode = "debug"
        return self.with_command("sleep", args=["infinity"])

    def _get_dependencies(self):
        if not self.config.namespace:
            raise ValueError("Namespace must be set before building dependencies")
        return {
            "services": [self.build_service()],
            "roles": [self.build_role()],
            "role_bindings": [self.build_rolebinding()],
            "config_maps": [self.build_config_map()],
        }


def apply_command_config(config: CommandConfig, mode: ScriptMode = "server"):
    try:
        command = config.find_command("python")
    except CommandNotFoundError as e:
        config.commands.append(Command(command="python", args=["/app/api_requester.py"]))
        command = config.find_command("python")

    command.add_args(
        [
            ("--mode", mode),
            ("--config", "/mount/config.yaml"),
        ],
        on_duplicate="replace",
    )


def apply_container_config(
    container: ContainerConfig,
    container_name: str,
    image: Image,
    mode: Optional[ScriptMode] = None,
) -> ContainerConfig:
    container.name = container_name
    container.with_image(image=image, overwrite=True)

    container.image_pull_policy = "Always"
    container.ports = [
        V1ContainerPort(8645),
        V1ContainerPort(8008),
        V1ContainerPort(8080),
    ]
    container.with_volume_mount(
        V1VolumeMount(name="api-requester-config-volume", mount_path="/mount"), overwrite=True
    )
    if mode is not None:
        apply_command_config(container.command_config, mode)

    return container


def apply_pod_spec_config(
    namespace: str, container_name: str, image: Image, config: PodSpecConfig
) -> PodSpecConfig:
    container = find_container_config(config, container_name)
    apply_container_config(container, container_name, image)
    config.dns_config = V1PodDNSConfig(
        searches=[f"zerotesting-publisher.{namespace}.svc.cluster.local"]
    )
    config.with_volume(
        V1Volume(
            name="api-requester-config-volume",
            config_map=V1ConfigMapVolumeSource(name="api-requester-config"),
        ),
        overwrite=True,
    )
    return config


def apply_pod_config(
    namespace: str, container_name: str, image: Image, config: PodConfig
) -> PodConfig:
    config.name = "publisher"
    config.namespace = namespace
    apply_pod_spec_config(
        namespace=namespace,
        container_name=container_name,
        image=image,
        config=config.pod_spec_config,
    )
    config.with_app("zerotenkay-publisher", overwrite=True)
    return config


def create_resources() -> V1ResourceRequirements:
    return V1ResourceRequirements(
        requests={"memory": "64Mi", "cpu": "150m"},
        limits={"memory": "600Mi", "cpu": "400m"},
    )
