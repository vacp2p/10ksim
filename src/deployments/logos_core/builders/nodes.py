# Python Imports
from typing import Optional

from kubernetes.client import (
    V1ContainerPort,
    V1EnvVar,
    V1EnvVarSource,
    V1ObjectFieldSelector,
    V1PodDNSConfig,
    V1ResourceRequirements,
)


from typing import Optional, Self

from pydantic import Field


# Project Imports
from src.deployments.core.configs.container import ContainerConfig, Image
from src.deployments.core.configs.pod import PodSpecConfig, PodTemplateSpecConfig
from src.deployments.core.configs.statefulset import StatefulSetSpecConfig
from src.deployments.core.builders import StatefulSetBuilder
from src.deployments.core.configs.container import ContainerConfig, Image
from src.deployments.core.configs.helpers.identity import apply_identity
from src.deployments.core.configs.helpers.utils import find_container_config, get_config
from src.deployments.core.configs.pod import PodSpecConfig


class NodesBuilder(StatefulSetBuilder):
    _service_name: str = "logos-core-service"
    _service_account_name: str = "secret-creator"
    _container_name: str = "logos-core-container"
    _name: str = "logoscore"
    _namespace: Optional[str] = None
    _image: Image = Field(
        default_factory=lambda: Image(repo="pearsonwhite/dst-lc-api", tag="wip2-amd")
    )
    _app: str = "zerotenkay-core"

    def with_config(self, namespace: str, name: str) -> Self:
        self._name = name
        self._namespace = namespace
        self._reconcile()
        return self

    def with_app(self, app: str) -> Self:
        self._app = app
        self._reconcile()
        return self

    def _reconcile(self):
        apply_identity(self.config, self._name, self._namespace, self._app)
        self._ensure_container()
        container_config = find_container_config(self.config, self._container_name)
        apply_container_config(container_config, self._image)

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
            pod_config.add_container(ContainerConfig(name=self._container_name))

    def with_image(self, image: Image) -> Self:
        self._image = image
        self.with_image_in_container(self._container_name, self._image, overwrite=True)
        return self


def apply_container_config(
    config: ContainerConfig, container_name: str, image: Image
) -> ContainerConfig:
    config.name = (container_name,)
    config.with_image(image)
    config.with_port(V1ContainerPort(containerPort=8645))
    config.with_port(V1ContainerPort(containerPort=8008))
    config.with_port(V1ContainerPort(containerPort=8080))
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

