# Python Imports
from typing import Optional, Self

from kubernetes.client import (
    V1ContainerPort,
    V1EnvVar,
    V1EnvVarSource,
    V1ObjectFieldSelector,
    V1ObjectMeta,
    V1ResourceRequirements,
    V1Service,
    V1ServicePort,
    V1ServiceSpec,
)
from pydantic import PrivateAttr

from src.deployments.core.builders import StatefulSetBuilder

# Project Imports
from src.deployments.core.configs.container import ContainerConfig, Image
from src.deployments.core.configs.helpers.identity import apply_identity
from src.deployments.core.configs.helpers.utils import find_container_config, get_config
from src.deployments.core.configs.pod import PodSpecConfig


class NodesBuilder(StatefulSetBuilder):
    _service_name: str = PrivateAttr(default="logos-core-service")
    _service_account_name: str = PrivateAttr(default="secret-creator")
    _container_name: str = PrivateAttr(default="logos-core-container")
    _name: str = PrivateAttr(default="logoscore")
    _namespace: Optional[str] = PrivateAttr(default=None)
    _image: Image = PrivateAttr(
        default_factory=lambda: Image(repo="pearsonwhite/dst-lc-node", tag="wip3-amd")
    )
    _app: str = PrivateAttr(default="zerotenkay-core")

    def with_config(self, namespace: str, name: Optional[str] = None) -> Self:
        if name is not None:
            self._name = name
        self._namespace = namespace
        self._reconcile()
        return self

    def with_app(self, app: str) -> Self:
        self._app = app
        self._reconcile()
        return self

    def build_dependencies(self) -> dict:
        service = V1Service(
            api_version="v1",
            kind="Service",
            metadata=V1ObjectMeta(
                name="core-nodes-internal",
                namespace=self._namespace,
            ),
            spec=V1ServiceSpec(
                cluster_ip="None",
                selector={"app": "zerotenkay-core"},
                ports=[V1ServicePort(port=8645, name="main", target_port=8645)],
            ),
        )
        return {"services": [service]}

    def _reconcile(self):
        self.config.stateful_set_spec.with_service_name(self._service_name)
        self.config.stateful_set_spec.pod_template_spec_config.pod_spec_config.with_service_account_name(
            "secret-creator2"
        )
        apply_identity(self.config, self._name, self._namespace, self._app)
        self._ensure_container()
        container_config = find_container_config(self.config, self._container_name)
        apply_container_config(container_config, self._container_name, self._image)

    def with_container_name(self, container_name: str) -> Self:
        self._ensure_container()
        container_config = find_container_config(self.config, self._container_name)
        self._container_name = container_name
        container_config.name = self._container_name
        return self

    def _ensure_container(self):
        container_config = find_container_config(self.config, self._container_name, default=None)
        if not container_config:
            pod_config = get_config(self.config, PodSpecConfig)
            pod_config.add_container(
                ContainerConfig(name=self._container_name, image_pull_policy="IfNotPresent")
            )

    def with_image(self, image: Image) -> Self:
        self._image = image
        self.with_image_in_container(self._container_name, self._image, overwrite=True)
        return self


def apply_container_config(
    config: ContainerConfig, container_name: str, image: Image
) -> ContainerConfig:
    config.name = container_name
    config.with_image(image)
    config.with_port(V1ContainerPort(container_port=8645), overwrite=True)
    config.with_port(V1ContainerPort(container_port=8008), overwrite=True)
    config.with_port(V1ContainerPort(container_port=8080), overwrite=True)
    config.with_resources(default_resources())

    # TODO: create readiness probe
    # config.with_readiness_probe()

    config.with_env_var(
        V1EnvVar(
            name="POD_NAME",
            value_from=V1EnvVarSource(field_ref=V1ObjectFieldSelector(field_path="metadata.name")),
        ),
        overwrite=True,
    )
    config.with_env_var(
        V1EnvVar(
            name="POD_UID",
            value_from=V1EnvVarSource(field_ref=V1ObjectFieldSelector(field_path="metadata.uid")),
        ),
        overwrite=True,
    )

    return config


def default_resources() -> V1ResourceRequirements:
    return V1ResourceRequirements(
        requests={"memory": "1Gi", "cpu": "500m"},
        limits={"memory": "4Gi", "cpu": "2000m"},
    )
