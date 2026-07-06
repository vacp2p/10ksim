# Python Imports
from typing import List, Optional, Self

from kubernetes.client import (
    V1ContainerPort,
    V1EnvVar,
    V1EnvVarSource,
    V1ObjectFieldSelector,
    V1ObjectMeta,
    V1PodSecurityContext,
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
    _service_name: str = PrivateAttr(default="core-nodes-internal")
    _service_account_name: str = PrivateAttr(default="secret-creator")
    _container_name: str = PrivateAttr(default="logos-core-container")
    _name: str = PrivateAttr(default="logoscore")
    _namespace: Optional[str] = PrivateAttr(default=None)
    _image: Image = PrivateAttr(
        default_factory=lambda: Image(repo="pearsonwhite/dst-lc-node", tag="wip3-amd")
    )
    _enrs: List[str] = PrivateAttr(default_factory=list)
    _dns_configs = PrivateAttr(default_factory=list)
    _app: str = PrivateAttr(default="zerotenkay-core")
    _debug: bool = PrivateAttr(default=False)

    def with_container_name(self, container_name: str) -> Self:
        self._ensure_container()
        container_config = find_container_config(self.config, self._container_name)
        self._container_name = container_name
        container_config.name = self._container_name
        return self

    def with_service_name(self, service_name: str) -> Self:
        self._service_name = service_name
        self._reconcile()
        return self

    def with_service_account_name(self, service_account_name: str) -> Self:
        self._service_account_name = service_account_name
        self._reconcile()
        return self

    def with_dns_service(self, searches) -> Self:
        self._dns_configs.extend(searches)
        self._reconcile()
        return self

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

    def with_enrs(
        self,
        enrs: List[str],
    ) -> Self:
        self._enrs.extend(enrs)
        self._ensure_container()
        self._reconcile()
        return self

    def build_dependencies(self) -> dict:
        service = V1Service(
            api_version="v1",
            kind="Service",
            metadata=V1ObjectMeta(
                name=self._service_name,
                namespace=self._namespace,
            ),
            spec=V1ServiceSpec(
                cluster_ip="None",
                selector={"app": self._app},
                ports=[V1ServicePort(port=8645, name="main", target_port=8645)],
            ),
        )
        return {"services": [service]}

    def with_debug(self, is_debug: bool = True) -> Self:
        self._debug = is_debug
        self._reconcile()
        return self

    def _reconcile(self):
        self.config.stateful_set_spec.with_service_name(self._service_name, overwrite=True)
        self.config.stateful_set_spec.pod_template_spec_config.pod_spec_config.with_service_account_name(
            self._service_account_name, overwrite=True
        )
        self.config.stateful_set_spec.pod_template_spec_config.pod_spec_config.dns_config = None
        for dns in self._dns_configs:
            search = f"{dns}.{self._namespace}.svc.cluster.local"
            self.config.stateful_set_spec.pod_template_spec_config.pod_spec_config.with_dns_search(
                search, overwrite=True
            )

        if self._debug:
            self.config.stateful_set_spec.pod_template_spec_config.pod_spec_config.with_security_context(
                V1PodSecurityContext(run_as_user=0, fs_group=0), overwrite=True
            )

        apply_identity(self.config, self._name, self._namespace, self._app)
        self._ensure_container()
        container_config = find_container_config(self.config, self._container_name)
        apply_container_config(container_config, self._container_name, self._image, self._enrs)

    def _ensure_container(self):
        container_config = find_container_config(self.config, self._container_name, default=None)
        if not container_config:
            pod_config = get_config(self.config, PodSpecConfig)
            pod_config.add_container(
                ContainerConfig(name=self._container_name, image_pull_policy="IfNotPresent")
            )

    def with_image(self, image: Image) -> Self:
        self._image = image
        self.with_image_in_container(
            image=self._image, container_name=self._container_name, overwrite=True
        )
        return self


def apply_container_config(
    config: ContainerConfig, container_name: str, image: Image, enrs: List[str]
) -> ContainerConfig:
    config.name = container_name
    config.with_image(image, overwrite=True)
    config.with_port(V1ContainerPort(container_port=8645), overwrite=True)
    config.with_port(V1ContainerPort(container_port=8008), overwrite=True)
    config.with_port(V1ContainerPort(container_port=8080), overwrite=True)
    config.with_resources(default_resources(), overwrite=True)

    # TODO: create readiness probe
    # config.with_readiness_probe()

    for index, enr in enumerate(enrs):
        config.with_env_var(
            V1EnvVar(
                name=f"ENR{index}",
                value=enr,
            ),
            overwrite=True,
        )

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
