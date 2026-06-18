from collections import defaultdict
from copy import deepcopy
from itertools import chain
from typing import Any, Dict, Optional, Self

from kubernetes.client import (
    RbacV1Subject,
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
)
from pydantic import Field, PrivateAttr

from src.deployments.core.configs.container import ContainerConfig
from src.deployments.core.configs.helpers.identity import apply_identity
from src.deployments.core.configs.helpers.utils import find_container_config, get_config
from src.deployments.core.configs.pod import PodSpecConfig
from src.deployments.core.k8s_object import V1Deployable
from src.deployments.pod_api_requester.builder import PodApiRequesterBuilder


class LogoscorePodApiRequester(PodApiRequesterBuilder):
    dependencies: Dict[str, Any] = Field(default_factory=dict)
    _service_account_name: str = PrivateAttr(default="secret-creator2")
    _secret_creator_role_name: str = PrivateAttr(default="secret-creator-role2")
    _secret_creator_binding_name: str = PrivateAttr(default="secret-creator-binding2")
    _pod_service_reader_binding_name_logoscore: str = PrivateAttr(
        default="pod-service-reader-binding-logoscore2"
    )
    _service_name: Optional[str] = PrivateAttr(default=None)
    _debug: bool = PrivateAttr(default=False)

    def with_namespace(self, namespace: str) -> Self:
        return super().with_namespace(namespace)

    def with_logoscore_profile(
        self,
        namespace: str,
        name: str = "logoscore2",
        app: str = "zerotenkay-core2",
        debug: bool = False,
    ) -> Self:
        self._namespace = namespace
        self._name = name
        self._app = app
        self._debug = debug
        self._reconcile()
        return self

    def with_service_account_name(self, service_account_name: str) -> Self:
        self._service_account_name = service_account_name
        self._reconcile()
        return self

    def with_secret_creator_role_name(self, role_name: str) -> Self:
        self._secret_creator_role_name = role_name
        return self

    def with_secret_creator_binding_name(self, binding_name: str) -> Self:
        self._secret_creator_binding_name = binding_name
        return self

    def with_pod_service_reader_binding_name(self, binding_name: str) -> Self:
        self._pod_service_reader_binding_name_logoscore = binding_name
        return self

    def with_service_name(self, service_name: str) -> Self:
        self._service_name = service_name
        self._reconcile()
        return self

    def _get_dependencies(self):
        base_dict = super()._get_dependencies()
        logoscore_dict = self._logoscore_dependencies()
        deps = defaultdict(list)
        for key, value in chain(base_dict.items(), logoscore_dict.items()):
            deps[key].extend(value)
        return dict(deps)

    def _logoscore_dependencies(self) -> dict:
        if not self._namespace:
            raise ValueError("Namespace must be set before building dependencies")
        if not self._service_account_name:
            raise ValueError("Service account name must be set before building dependencies")
        return {
            "roles": [role(self._namespace, self._secret_creator_role_name)],
            "role_bindings": role_bindings(
                self._namespace,
                self._service_account_name,
                self._secret_creator_binding_name,
                self._pod_service_reader_binding_name_logoscore,
                self._pod_service_reader_role_name,
                self._secret_creator_role_name,
            ),
            "service_accounts": [service_account(self._namespace, self._service_account_name)],
            "services": [service(self._namespace, self._service_name, self._app)],
        }

    def build_dependencies(self) -> Dict[str, V1Deployable]:
        self.dependencies = self._get_dependencies()
        return deepcopy(self.dependencies)

    def _reconcile(self) -> Self:
        if not self._namespace:
            return self

        apply_identity(self.config, name=self._name, namespace=self._namespace, app=self._app)

        self.config.pod_spec_config.with_service_account_name(
            self._service_account_name, overwrite=True
        )
        self.config.pod_spec_config.automount_service_account_token = True
        self.config.pod_spec_config.with_security_context(
            V1PodSecurityContext(run_as_user=0, fs_group=0), overwrite=True
        )

        if self._service_name:
            self.config.pod_spec_config.with_dns_service(
                f"{self._service_name}.{self._namespace}.svc.cluster.local", overwrite=True
            )

        container_config = find_container_config(
            self.config.pod_spec_config,
            self._container_name,
            default=None,
        )
        if not container_config:
            pod_config = get_config(self.config, PodSpecConfig)
            pod_config.add_container(
                ContainerConfig(
                    name=self._container_name,
                    image_pull_policy="IfNotPresent",
                )
            )
            container_config = find_container_config(
                self.config.pod_spec_config,
                self._container_name,
            )

        if not container_config.resources:
            container_config.with_resources(
                V1ResourceRequirements(
                    requests={"memory": "1Gi", "cpu": "500m"},
                    limits={"memory": "4Gi", "cpu": "2000m"},
                )
            )

        if self._debug:
            container_config.with_env_var(
                V1EnvVar(name="LOGGING_LEVEL", value="DEBUG"),
                overwrite=True,
            )

        return self


def service_account(namespace: str, service_account_name: str):
    return V1ServiceAccount(
        api_version="v1",
        kind="ServiceAccount",
        metadata=V1ObjectMeta(name=service_account_name, namespace=namespace),
    )


def role(namespace: str, role_name: str):
    return V1Role(
        api_version="rbac.authorization.k8s.io/v1",
        kind="Role",
        metadata=V1ObjectMeta(
            name=role_name,
            namespace=namespace,
        ),
        rules=[
            V1PolicyRule(
                api_groups=[""],
                resources=["secrets"],
                verbs=["create", "get", "update"],
            )
        ],
    )


def role_bindings(
    namespace: str,
    service_account_name: str,
    secret_creator_binding_name: str,
    pod_service_reader_binding_name: str,
    pod_service_reader_role_name: str,
    secret_creator_role_name: str,
):
    secret_role_binding = V1RoleBinding(
        api_version="rbac.authorization.k8s.io/v1",
        kind="RoleBinding",
        metadata=V1ObjectMeta(
            name=secret_creator_binding_name,
            namespace=namespace,
        ),
        subjects=[
            RbacV1Subject(
                kind="ServiceAccount",
                name=service_account_name,
                namespace=namespace,
            )
        ],
        role_ref=V1RoleRef(
            kind="Role",
            name=secret_creator_role_name,
            api_group="rbac.authorization.k8s.io",
        ),
    )
    role_binding = V1RoleBinding(
        api_version="rbac.authorization.k8s.io/v1",
        kind="RoleBinding",
        metadata=V1ObjectMeta(
            name=pod_service_reader_binding_name,
            namespace=namespace,
        ),
        subjects=[
            RbacV1Subject(
                kind="ServiceAccount",
                name=service_account_name,
                namespace=namespace,
            )
        ],
        role_ref=V1RoleRef(
            kind="Role",
            name=pod_service_reader_role_name,
            api_group="rbac.authorization.k8s.io",
        ),
    )
    return [secret_role_binding, role_binding]


def service(namespace: str, service_name: str, app: str) -> V1Service:
    return V1Service(
        api_version="v1",
        kind="Service",
        metadata=V1ObjectMeta(name=service_name, namespace=namespace),
        spec=V1ServiceSpec(
            type="NodePort",
            selector={"app": app},
            ports=[
                V1ServicePort(
                    protocol="TCP",
                    port=8000,
                    target_port=8645,
                )
            ],
        ),
    )
