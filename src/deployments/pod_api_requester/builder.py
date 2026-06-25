import logging
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Literal, Optional, Self

import yaml
from kubernetes.client import (
    V1ConfigMap,
    V1ConfigMapVolumeSource,
    V1ContainerPort,
    V1EnvVar,
    V1ObjectMeta,
    V1Pod,
    V1PodDNSConfig,
    V1PolicyRule,
    V1ResourceRequirements,
    V1Role,
    V1RoleBinding,
    V1RoleRef,
    V1ServicePort,
    V1Volume,
    V1VolumeMount,
)
from pydantic import PrivateAttr

from src.deployments.core.base_bridge import V1Deployable
from src.deployments.core.builders import PodBuilder, ServiceBuilder
from src.deployments.core.configs.command import Command, CommandConfig
from src.deployments.core.configs.container import ContainerConfig, Image
from src.deployments.core.configs.helpers.identity import apply_identity
from src.deployments.core.configs.helpers.utils import find_container_config, get_config
from src.deployments.core.configs.pod import PodSpecConfig
from src.deployments.core.dependency_decorator import depends_on
from src.deployments.core.k8s_object import dict_to_k8s_object

ScriptMode = Literal["server", "batch", "debug"]

DEFAULT_REQUESTER_NAME = "publisher"
DEFAULT_REQUESTER_APP = "zerotenkay-publisher"
DEFAULT_REQUESTER_CONFIG_MAP_NAME = "api-requester-config"
DEFAULT_REQUESTER_VOLUME_NAME = "api-requester-config-volume"

logger = logging.getLogger(__name__)


@dataclass
class RequesterBaseParams:
    name: Optional[str] = None
    namespace: Optional[str] = None
    app: Optional[str] = None
    mode: Optional[ScriptMode] = None
    container_name: Optional[str] = None
    image: Optional[Image] = None
    service_name: Optional[str] = None
    requester_base_enabled: Optional[bool] = None
    requester_selector_app: Optional[str] = None
    pod_service_reader_role_name: Optional[str] = None
    pod_service_reader_binding_name: Optional[str] = None


class PodApiRequesterBuilder(PodBuilder):
    _mode: Optional[ScriptMode] = None

    _base_requester_params: Optional[RequesterBaseParams] = None

    # TODO: move to base class
    _restart_policy: Optional[Literal["Always", "OnFailure", "Never"]] = None

    _container_name: str = PrivateAttr(default="pod-api-requester-container")
    _image: Image = PrivateAttr(
        default_factory=lambda: Image(
            repo="pearsonwhite/pod-api-requester", tag="10b85bb60895fe63aa8d3f09b24b714f2abce300"
        )
    )
    _service_name: str = PrivateAttr(default="zerotesting-publisher")

    _requester_base_enabled: bool = PrivateAttr(default=False)
    _requester_selector_app: Optional[str] = PrivateAttr(default="zerotenkay-publisher")
    _pod_service_reader_role_name: Optional[str] = PrivateAttr(default="pod-service-reader")
    _pod_service_reader_binding_name: Optional[str] = PrivateAttr(
        default="pod-service-reader-binding"
    )

    def model_post_init(self, __context) -> None:
        super().model_post_init(__context)

        # Enabled by default. Base feature.
        self._enable_requester_base()

    @property
    def service_name(self) -> Optional[str]:
        return self._service_name

    @service_name.setter
    def service_name(self, value: Optional[str]) -> None:
        self._service_name = value
        self._reconcile("service_name")

    def _enable_requester_base(self) -> None:
        self._set_requester_defaults()
        self._requester_base_enabled = True
        self._reconcile("_requester_base_enabled")

    def _set_requester_defaults(self) -> None:
        if self.name is None:
            self.name = DEFAULT_REQUESTER_NAME
        if self.app is None:
            self.app = DEFAULT_REQUESTER_APP

    @depends_on(
        "_requester_base_enabled",
        "namespace",
        "name",
        "app",
        "_container_name",
        "_requester_selector_app",
        "_pod_service_reader_role_name",
        "_pod_service_reader_binding_name",
        "_image",
        "_mode",
        "service_name",
    )
    def _apply_requester_base(self):
        if not self._requester_base_enabled:
            return self

        new_params = _build_requester_base_params(self)
        self._apply_requester_base_inner(
            old_params=self._base_requester_params, new_params=new_params
        )
        self._base_requester_params = new_params
        return self

    def _apply_requester_base_inner(
        self, old_params: RequesterBaseParams, new_params: RequesterBaseParams
    ):
        config = self.config

        apply_identity(
            config, name=new_params.name, namespace=new_params.namespace, app=new_params.app
        )
        pod_spec_config = config.pod_spec_config
        pod_spec_config.dns_config = V1PodDNSConfig(
            searches=[f"{new_params.service_name}.{new_params.namespace}.svc.cluster.local"]
        )
        pod_spec_config.with_volume(
            V1Volume(
                name=DEFAULT_REQUESTER_VOLUME_NAME,
                config_map=V1ConfigMapVolumeSource(name=DEFAULT_REQUESTER_CONFIG_MAP_NAME),
            ),
            overwrite=True,
        )

        self._ensure_container()
        container = find_container_config(config, new_params.container_name)
        container.name = new_params.container_name
        if not container.resources:
            container.with_resources(
                V1ResourceRequirements(
                    requests={"memory": "1Gi", "cpu": "500m"},
                    limits={"memory": "4Gi", "cpu": "2000m"},
                )
            )
        container.with_image(image=new_params.image, overwrite=True)
        container.image_pull_policy = "Always"
        container.ports = [
            V1ContainerPort(8645),
            V1ContainerPort(8008),
            V1ContainerPort(8080),
        ]
        container.with_volume_mount(
            V1VolumeMount(name=DEFAULT_REQUESTER_VOLUME_NAME, mount_path="/mount"), overwrite=True
        )
        if new_params.mode == "debug":
            container.with_env_var(
                V1EnvVar(name="LOGGING_LEVEL", value="DEBUG"),
                overwrite=True,
            )

        def command_from_mode(mode):
            if mode == "debug":
                return Command("sleep", args=["infinity"])
            else:
                return Command(
                    command="python",
                    args=[
                        "/app/api_requester.py",
                        ("--mode", mode),
                        ("--config", "/mount/config.yaml"),
                    ],
                )

        command_config = container.command_config
        if old_params and old_params.mode:
            old_command = command_from_mode(old_params.mode)
            command_config.commands.remove(old_command)
        new_command = command_from_mode(new_params.mode)
        command_config.commands.append(new_command)

    def _ensure_container(self):
        container_config = find_container_config(self.config, self._container_name, default=None)
        if not container_config:
            pod_config = get_config(self.config, PodSpecConfig)
            pod_config.add_container(
                ContainerConfig(name=self._container_name, image_pull_policy="IfNotPresent")
            )

    def with_container_name(self, container_name: str) -> Self:
        self._container_name = container_name
        self._reconcile("_container_name")
        return self

    def with_image(self, image: Image) -> Self:
        self._image = image
        self._reconcile("_image")
        return self

    def with_service_name(self, service_name: str) -> Self:
        self.service_name = service_name
        return self

    def with_requester_selector_app(self, app: str) -> Self:
        self.requester_selector_app = app
        return self

    def with_mode(self, mode: ScriptMode) -> Self:
        self._mode = mode
        self._reconcile("_mode")
        return self

    def with_command(self, command: str, args: List[str]) -> Self:
        container_config = find_container_config(self.config.pod_spec_config, self._container_name)
        container_config.command_config = CommandConfig(
            commands=[Command(command=command, args=args)]
        )
        return self

    def with_dns_search(self, search, *, overwrite: bool = False) -> Self:
        self.config.pod_spec_config.with_dns_search(search, overwrite=overwrite)
        self._reconcile("dns_search")
        return self

    def with_debug(self) -> Self:
        self._mode = "debug"
        return self.with_command("sleep", args=["infinity"])

    def build_role(self) -> V1Role:
        return V1Role(
            api_version="rbac.authorization.k8s.io/v1",
            kind="Role",
            metadata=V1ObjectMeta(
                name=self._pod_service_reader_role_name,
                namespace=self.namespace,
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
                namespace=self.namespace,
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
                    "namespace": self.namespace,
                },
            ],
        )

    def build_config_map(self) -> V1ConfigMap:
        with open(Path(__file__).parent / "config.yaml", "r") as config_file:
            config_dict = yaml.safe_load(config_file.read())
        config_map: V1ConfigMap = dict_to_k8s_object(config_dict, "V1ConfigMap")
        config_map.metadata.namespace = self.namespace
        return config_map

    def build(self) -> V1Pod:
        if not self.name:
            raise ValueError(f"Must configure node first. Config: `{self.config}`")
        if not self._mode:
            raise ValueError(
                f"Script mode must be set using `with_mode` before building. Config: `{self.config}`"
            )

        pod = super().build()

        if self._restart_policy:
            pod.spec.restart_policy = self._restart_policy
        elif self._mode == "batch":
            pod.spec.restart_policy = "Never"

        return pod

    def build_dependencies(self) -> Dict[str, V1Deployable]:
        self.dependencies = self._get_dependencies()
        return deepcopy(self.dependencies)

    def _get_dependencies(self):
        if not self.namespace:
            raise ValueError("Namespace must be set before building dependencies")

        service = (
            ServiceBuilder()
            .with_namespace(self.namespace)
            .with_name(self._service_name)
            .with_selector("app", self.app)
            .with_type("NodePort")
            .with_port(
                V1ServicePort(
                    protocol="TCP",
                    port=8000,
                    target_port=8645,
                )
            )
            .build()
        )
        return {
            "services": [service],
            "roles": [self.build_role()],
            "role_bindings": [self.build_rolebinding()],
            "config_maps": [self.build_config_map()],
        }


def _build_requester_base_params(builder: PodApiRequesterBuilder) -> RequesterBaseParams:
    return RequesterBaseParams(
        name=builder.name,
        namespace=builder.namespace,
        app=builder.app,
        mode=builder._mode,
        container_name=builder._container_name,
        requester_base_enabled=builder._requester_base_enabled,
        requester_selector_app=builder._requester_selector_app,
        image=builder._image,
        pod_service_reader_binding_name=builder._pod_service_reader_binding_name,
        pod_service_reader_role_name=builder._pod_service_reader_role_name,
        service_name=builder.service_name,
    )
