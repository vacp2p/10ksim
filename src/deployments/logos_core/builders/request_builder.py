from collections import defaultdict
from copy import deepcopy
from itertools import chain
from typing import Any, Dict, Self

from kubernetes.client import (
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
from src.deployments.core.k8s_object import V1Deployable
from src.deployments.pod_api_requester.builder import NAME, PodApiRequesterBuilder


class LogoscorePodApiRequester(PodApiRequesterBuilder):
    dependencies: Dict[str, Any] = Field(default_factory=dict)

    def with_logoscore_profile(
        self,
        namespace: str,
        name: str = "logoscore2",
        app: str = "zerotenkay-core2",
        debug: bool = False,
    ) -> Self:
        apply_logoscore_profile(self.config, namespace=namespace, name=name, app=app, debug=debug)
        self.dependencies = self._get_dependencies()
        return self

    def _get_dependencies(self):
        base_dict = super()._get_dependencies()
        logoscore_dict = self._logoscore_dependencies()
        deps = defaultdict(list)
        for key, value in chain(base_dict.items(), logoscore_dict.items()):
            deps[key].extend(value)
        return dict(deps)

    def _logoscore_dependencies(self) -> dict:
        if not self.config.namespace:
            raise ValueError("Namespace must be set before building dependencies")
        return {
            "roles": [role(self.config.namespace)],
            "role_bindings": role_bindings(self.config.namespace),
            "service_accounts": [service_account(self.config.namespace)],
            "services": [service(self.config.namespace)],
        }

    def build_dependencies(self) -> Dict[str, V1Deployable]:
        return deepcopy(self.dependencies)


def service_account(namespace: str):
    return V1ServiceAccount(
        api_version="v1",
        kind="ServiceAccount",
        metadata=V1ObjectMeta(name="secret-creator2", namespace=namespace),
    )


def role(namespace: str):
    return V1Role(
        api_version="rbac.authorization.k8s.io/v1",
        kind="Role",
        metadata=V1ObjectMeta(name="secret-creator-role2", namespace=namespace),
        rules=[
            V1PolicyRule(api_groups=[""], resources=["secrets"], verbs=["create", "get", "update"])
        ],
    )


def role_bindings(namespace: str):
    secret_role_binding = V1RoleBinding(
        api_version="rbac.authorization.k8s.io/v1",
        kind="RoleBinding",
        metadata=V1ObjectMeta(name="secret-creator-binding2", namespace=namespace),
        subjects=[V1Subject(kind="ServiceAccount", name="secret-creator2", namespace=namespace)],
        role_ref=V1RoleRef(
            kind="Role", name="secret-creator-role2", api_group="rbac.authorization.k8s.io"
        ),
    )
    role_binding = V1RoleBinding(
        api_version="rbac.authorization.k8s.io/v1",
        kind="RoleBinding",
        metadata=V1ObjectMeta(
            name="pod-service-reader-binding-logoscore2",
            namespace=namespace,
        ),
        subjects=[
            V1Subject(
                kind="ServiceAccount",
                name="secret-creator2",
                namespace=namespace,
            )
        ],
        role_ref=V1RoleRef(
            kind="Role", name="pod-service-reader", api_group="rbac.authorization.k8s.io"
        ),
    )
    return [secret_role_binding, role_binding]


def service(namespace: str) -> V1Service:
    return V1Service(
        api_version="v1",
        kind="Service",
        metadata=V1ObjectMeta(name="core-external", namespace=namespace),
        spec=V1ServiceSpec(
            type="NodePort",
            selector={"app": "zerotenkay-core2"},
            ports=[
                V1ServicePort(
                    protocol="TCP",
                    port=8000,
                    target_port=8645,
                )
            ],
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

    config.pod_spec_config.with_service_account_name("secret-creator2")
    config.pod_spec_config.automount_service_account_token = True
    config.pod_spec_config.with_security_context(V1PodSecurityContext(run_as_user=0, fs_group=0))
    config.pod_spec_config.with_dns_service(f"core-nodes-internal.{namespace}.svc.cluster.local")

    # TODO: change to use self._container_name when updating PodApiRequesterBuilder.
    container_config = find_container_config(config.pod_spec_config, NAME)
    container_config.name = "logos-core-container"

    container_config.with_resources(
        V1ResourceRequirements(
            requests={"memory": "1Gi", "cpu": "500m"}, limits={"memory": "4Gi", "cpu": "2000m"}
        )
    )
    logoscore_image = Image(repo="pearsonwhite/dst-lc-api", tag="1-amd")
    container_config.with_image(logoscore_image, overwrite=True)
    if debug:
        container_config.with_env_var(V1EnvVar(name="LOGGING_LEVEL", value="DEBUG"), overwrite=True)
