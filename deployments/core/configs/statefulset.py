from typing import Dict, List, Literal, Optional, TypeVar

from kubernetes.client import (
    V1LabelSelector,
    V1ObjectMeta,
    V1PersistentVolumeClaim,
    V1StatefulSet,
    V1StatefulSetSpec,
)
from pydantic import BaseModel, ConfigDict, Field

from core.configs.pod import PodTemplateSpecConfig, build_pod_template_spec

T = TypeVar("T")


class StatefulSetSpecConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    replicas: Optional[int] = 1
    selector_labels: Optional[Dict[str, str]] = None
    service_name: Optional[str] = None
    pod_template_spec_config: PodTemplateSpecConfig = PodTemplateSpecConfig()
    volume_claim_templates: Optional[List[V1PersistentVolumeClaim]] = None

    def with_service_name(self, service_name: str, *, overwrite: bool = False):
        if self.service_name is not None and not overwrite:
            raise ValueError(
                f"Service name already set in {type(self)}. Passed service_name `{service_name}` Config: `{self}`"
            )
        self.service_name = service_name

    def with_app(self, app: str, *, overwrite: bool = False):
        if self.selector_labels is not None and not overwrite:
            if app in self.selector_labels:
                raise ValueError(
                    f"{type(self)} already has app in selector labels. Passed app`{app}` Config: `{self}`"
                )
        if self.selector_labels is None:
            self.selector_labels = {}
        self.selector_labels["app"] = app


class StatefulSetConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: Optional[str] = None
    namespace: Optional[str] = None
    apiVersion: Optional[str] = Field(default="apps/v1")
    kind: Optional[str] = Field(default="StatefulSet")
    labels: Optional[Dict[str, str]] = None
    stateful_set_spec: StatefulSetSpecConfig = StatefulSetSpecConfig()
    pod_management_policy: Optional[Literal["Parallel", "OrderedReady"]] = None


def build_stateful_set(config: StatefulSetConfig) -> V1StatefulSet:
    return V1StatefulSet(
        api_version=config.apiVersion,
        kind=config.kind,
        metadata=V1ObjectMeta(name=config.name, namespace=config.namespace, labels=config.labels),
        spec=V1StatefulSetSpec(
            replicas=config.stateful_set_spec.replicas,
            pod_management_policy=config.pod_management_policy,
            selector=V1LabelSelector(match_labels=config.stateful_set_spec.selector_labels),
            service_name=config.stateful_set_spec.service_name,
            template=build_pod_template_spec(config.stateful_set_spec.pod_template_spec_config),
            volume_claim_templates=config.stateful_set_spec.volume_claim_templates,
        ),
    )
