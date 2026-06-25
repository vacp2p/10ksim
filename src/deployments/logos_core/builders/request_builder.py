from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Self

from kubernetes.client import (
    RbacV1Subject,
    V1ObjectMeta,
    V1PodSecurityContext,
    V1PolicyRule,
    V1Role,
    V1RoleBinding,
    V1RoleRef,
    V1ServiceAccount,
)
from pydantic import Field, PrivateAttr

from src.deployments.core.configs.helpers.identity import apply_identity
from src.deployments.core.configs.helpers.utils import find_container_config
from src.deployments.pod_api_requester.builder import (
    PodApiRequesterBuilder,
)
from src.deployments.core.dependency_decorator import depends_on


@dataclass
class LogoscoreParams:
    namespace: Optional[str] = None
    name: Optional[str] = None
    app: Optional[str] = None
    service_name: Optional[str] = None
    debug: bool = False
    service_account_name: Optional[str] = None
    secret_creator_role_name: Optional[str] = None
    secret_creator_binding_name: Optional[str] = None
    pod_service_reader_binding_name: Optional[str] = None
    pod_service_reader_role_name: Optional[str] = None


class LogoscorePodApiRequester(PodApiRequesterBuilder):
    dependencies: Dict[str, Any] = Field(default_factory=dict)

    _logoscore_enabled: bool = PrivateAttr(default=False)
    _logoscore_params: Optional[LogoscoreParams] = PrivateAttr(default=None)
    _logoscore_dependencies: Dict[str, Any] = PrivateAttr(default_factory=dict)

    _service_account_name: object = PrivateAttr(default="secret-creator2")
    _secret_creator_role_name: object = PrivateAttr(default="secret-creator-role2")
    _secret_creator_binding_name: object = PrivateAttr(default="secret-creator-binding2")
    _pod_service_reader_role_name: str = "pod-service-reader"
    _pod_service_reader_binding_name_logoscore: object = PrivateAttr(
        default="pod-service-reader-binding-logoscore2"
    )
    _debug: bool = PrivateAttr(default=False)

    @property
    def service_account_name(self) -> Optional[str]:
        return self._service_account_name

    @service_account_name.setter
    def service_account_name(self, value: Optional[str]) -> None:
        self._service_account_name = value
        self._reconcile("service_account_name")

    @property
    def secret_creator_role_name(self) -> Optional[str]:
        return self._secret_creator_role_name

    @secret_creator_role_name.setter
    def secret_creator_role_name(self, value: Optional[str]) -> None:
        self._secret_creator_role_name = value
        self._reconcile("secret_creator_role_name")

    @property
    def secret_creator_binding_name(self) -> Optional[str]:
        return self._secret_creator_binding_name

    @secret_creator_binding_name.setter
    def secret_creator_binding_name(self, value: Optional[str]) -> None:
        self._secret_creator_binding_name = value
        self._reconcile("secret_creator_binding_name")

    @property
    def pod_service_reader_binding_name(self) -> Optional[str]:
        return self._pod_service_reader_binding_name_logoscore

    @pod_service_reader_binding_name.setter
    def pod_service_reader_binding_name(self, value: Optional[str]) -> None:
        self._pod_service_reader_binding_name_logoscore = value
        self._reconcile("pod_service_reader_binding_name")

    @property
    def debug(self) -> bool:
        return self._debug

    @debug.setter
    def debug(self, value: bool) -> None:
        self._debug = value
        self._reconcile("debug")

    @property
    def logoscore_enabled(self) -> bool:
        return self._logoscore_enabled

    @logoscore_enabled.setter
    def logoscore_enabled(self, logoscore_enabled: bool) -> None:
        self._logoscore_enabled = logoscore_enabled
        self._reconcile("logoscore_enabled")

    def with_logoscore(self) -> Self:
        self.logoscore_enabled = True
        return self

    def with_service_account_name(self, service_account_name: str) -> Self:
        self.service_account_name = service_account_name
        return self

    def with_secret_creator_role_name(self, role_name: str) -> Self:
        self.secret_creator_role_name = role_name
        return self

    def with_secret_creator_binding_name(self, binding_name: str) -> Self:
        self.secret_creator_binding_name = binding_name
        return self

    def with_pod_service_reader_binding_name(self, binding_name: str) -> Self:
        self.pod_service_reader_binding_name = binding_name
        return self

    def with_debug(self, debug: bool = True) -> Self:
        self.debug = debug
        self._reconcile("debug")
        return self

    @depends_on(
        "logoscore_enabled",
        "namespace",
        "name",
        "app",
        "service_name",
        "debug",
        "service_account_name",
        "secret_creator_role_name",
        "secret_creator_binding_name",
        "pod_service_reader_binding_name",
    )
    def _apply_logoscore(self):
        new_params = LogoscoreParams(
            namespace=self.namespace,
            name=self.name,
            app=self.app,
            service_name=self.service_name,
            debug=self._debug,
            service_account_name=self._service_account_name,
            secret_creator_role_name=self._secret_creator_role_name,
            secret_creator_binding_name=self._secret_creator_binding_name,
            pod_service_reader_binding_name=self._pod_service_reader_binding_name_logoscore,
            pod_service_reader_role_name=self._pod_service_reader_role_name,
        )
        self._apply_logoscore_inner(old_params=self._logoscore_params, new_params=new_params)
        self._logoscore_params = new_params
        return self

    def _apply_logoscore_inner(
        self, old_params: LogoscoreParams, new_params: LogoscoreParams
    ) -> Self:
        pod_spec = self.config.pod_spec_config

        if old_params and old_params.service_name and old_params.namespace:
            old_search = f"{old_params.service_name}.{old_params.namespace}.svc.cluster.local"
            pod_spec.remove_dns_search(old_search, missing_ok=True)

        new_search = f"{new_params.service_name}.{new_params.namespace}.svc.cluster.local"
        pod_spec.with_dns_search(new_search, overwrite=True)

        apply_identity(
            self.config, name=new_params.name, namespace=new_params.namespace, app=new_params.app
        )

        pod_spec.with_service_account_name(new_params.service_account_name, overwrite=True)
        pod_spec.automount_service_account_token = True
        pod_spec.with_security_context(
            V1PodSecurityContext(run_as_user=0, fs_group=0), overwrite=True
        )

        self._ensure_container()
        container_config = find_container_config(
            self.config.pod_spec_config,
            self._container_name,
            default=None,
        )

        self._logoscore_dependencies["service_account"] = V1ServiceAccount(
            api_version="v1",
            kind="ServiceAccount",
            metadata=V1ObjectMeta(
                name=new_params.service_account_name, namespace=new_params.namespace
            ),
        )
        self._logoscore_dependencies["roles"] = [
            role(new_params.namespace, new_params.secret_creator_role_name)
        ]
        self._logoscore_dependencies["role_bindings"] = role_bindings(new_params)

        return self

    def _get_dependencies(self):
        base_dict = super()._get_dependencies()
        base_dict["logoscore"] = self._logoscore_dependencies
        return base_dict


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


def role_bindings(params: LogoscoreParams):
    secret_role_binding = V1RoleBinding(
        api_version="rbac.authorization.k8s.io/v1",
        kind="RoleBinding",
        metadata=V1ObjectMeta(
            name=params.secret_creator_binding_name,
            namespace=params.namespace,
        ),
        subjects=[
            RbacV1Subject(
                kind="ServiceAccount",
                name=params.service_account_name,
                namespace=params.namespace,
            )
        ],
        role_ref=V1RoleRef(
            kind="Role",
            name=params.secret_creator_role_name,
            api_group="rbac.authorization.k8s.io",
        ),
    )
    role_binding = V1RoleBinding(
        api_version="rbac.authorization.k8s.io/v1",
        kind="RoleBinding",
        metadata=V1ObjectMeta(
            name=params.pod_service_reader_binding_name,
            namespace=params.namespace,
        ),
        subjects=[
            RbacV1Subject(
                kind="ServiceAccount",
                name=params.service_account_name,
                namespace=params.namespace,
            )
        ],
        role_ref=V1RoleRef(
            kind="Role",
            name=params.pod_service_reader_role_name,
            api_group="rbac.authorization.k8s.io",
        ),
    )
    return [secret_role_binding, role_binding]
