from typing import Dict, List, Literal, Optional, TypeVar

from kubernetes.client import (
    V1PersistentVolumeClaim,
)
from pydantic import BaseModel, ConfigDict

from builders.configs.pod import PodTemplateSpecConfig

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
    apiVersion: Optional[str] = None
    kind: Optional[str] = None
    labels: Optional[Dict[str, str]] = None
    stateful_set_spec: StatefulSetSpecConfig = StatefulSetSpecConfig()
    pod_management_policy: Optional[Literal["Parallel", "OrderedReady"]] = None
