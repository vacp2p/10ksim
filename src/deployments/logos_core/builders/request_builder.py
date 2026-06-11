from copy import deepcopy
from typing import Any, Dict, Self

from kubernetes.client import (
    V1Object,
    V1EnvVar,
    V1ObjectMeta,
    V1PodSecurityContext,
    V1PolicyRule,
    V1ResourceRequirements,
    V1Role,
    V1RoleBinding,
    V1RoleRef,
    V1Service,
    V1ServiceAccount,
    V1ServicePort,
    V1ServiceSpec,
    V1Subject,
)
from pydantic import Field

from src.deployments.core.configs.container import Image
from src.deployments.core.configs.helpers.identity import apply_identity
from src.deployments.core.configs.helpers.utils import find_container_config
from src.deployments.core.configs.pod import PodConfig
from src.deployments.pod_api_requester.builder import NAME, PodApiRequesterBuilder


class LogoscorePodApiRequester(PodApiRequesterBuilder):
    namespace: str
    dependencies: Dict[str, Any] = Field(default_factory=dict)

    def with_logoscore_profile(
        self,
        namespace: str,
        name: str = "logoscore2",
        app: str = "zerotenkay-core2",
        debug: bool = False,
    ) -> Self:
        apply_logoscore_profile(self.config, namespace, name, app, debug)
        self.dependencies.update(self._logoscore_dependencies())
        return self

    def _logoscore_dependencies(self) -> dict:
        # TODO: add normal pod-api-requester deps
        if not self.config.namespace:
            raise ValueError("Namespace must be set before building dependencies")
        return {
            "services": [service(self.namespace)],
            "role": [role(self.namespace)],
            "role_binding": [role_binding(self.name)],
            "service_account": [service_account(self.name)],
        }

    def build_dependencies(self) -> Dict[str, V1Object]:
        return deepcopy(self.dependencies)



def service(namespace: str, name: str):
    return V1Service(
        api_version="v1",
        kind="Service",
        metadata=V1ObjectMeta(name=name, namespace=namespace),
        spec=V1ServiceSpec(
            type="NodePort",
            selector={"app": "zerotenkay-core"},
            ports=[V1ServicePort(protocol="TCP", port=8088, target_port=8645, node_port=30088)],
        ),
    )


def service_account(namespace: str):
    return V1ServiceAccount(
        api_version="v1",
        kind="ServiceAccount",
        metadata=V1ObjectMeta(name="secret-creator", namespace=namespace),
    )


def role(namespace: str):
    return V1Role(
        api_version="rbac.authorization.k8s.io/v1",
        kind="Role",
        metadata=V1ObjectMeta(name="secret-creator-role", namespace=namespace),
        rules=[
            V1PolicyRule(api_groups=[""], resources=["secrets"], verbs=["create", "get", "update"])
        ],
    )


def role_binding(namespace: str):
    return V1RoleBinding(
        api_version="rbac.authorization.k8s.io/v1",
        kind="RoleBinding",
        metadata=V1ObjectMeta(name="secret-creator-binding", namespace=namespace),
        subjects=[V1Subject(kind="ServiceAccount", name="secret-creator", namespace=namespace)],
        role_ref=V1RoleRef(
            kind="Role", name="secret-creator-role", api_group="rbac.authorization.k8s.io"
        ),
    )


def apply_logoscore_profile(
    config: PodConfig,
    namespace: str,
    name: str = "logoscore2",
    app: str = "zerotenkay-core2",
    debug: bool = False,
) -> Self:
    apply_identity(config, name=name, namespace=namespace, app=app)

    config.pod_spec_config.with_service_account_name("secret-creator")
    config.pod_spec_config.with_security_context(V1PodSecurityContext(run_as_user=0, fs_group=0))
    config.pod_spec_config.with_dns_service(f"core-nodes-internal.{namespace}.svc.cluster.local")
    config.pod_spec_config.with_dns_service(f"zerotesting-core2.{namespace}.svc.cluster.local")

    # TODO: change to use self._container_name when updating PodApiRequesterBuilder.
    container_config = find_container_config(config.pod_spec_config, NAME)
    container_config.name = "logos-core-container"

    container_config.with_resources(
        V1ResourceRequirements(
            requests={"memory": "1Gi", "cpu": "500m"}, limits={"memory": "4Gi", "cpu": "2000m"}
        )
    )
    logoscore_image = Image(repo="pearsonwhite/dst-lc-api", tag="wip2-amd")
    container_config.with_image(logoscore_image, overwrite=True)
    if debug:
        container_config.with_env_var(V1EnvVar(name="LOGGING_LEVEL", value="DEBUG"), overwrite=True)
