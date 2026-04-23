from typing import Dict, List, Optional

from kubernetes.client import V1ObjectMeta, V1Service, V1ServicePort, V1ServiceSpec
from pydantic import BaseModel, ConfigDict, Field


class ServiceSpecConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    cluster_ip: Optional[str] = None
    selector: Optional[Dict[str, str]] = None
    ports: Optional[List[V1ServicePort]] = None

    def with_selector(self, key: str, value: str):
        if self.selector is None:
            self.selector = {}
        self.selector[key] = value


class ServiceConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: Optional[str] = None
    namespace: Optional[str] = None
    apiVersion: Optional[str] = Field(default="v1")
    kind: Optional[str] = Field(default="Service")
    labels: Optional[Dict[str, str]] = None
    service_spec: ServiceSpecConfig = Field(default_factory=ServiceSpecConfig)


def build_service(config: ServiceConfig) -> V1Service:
    return V1Service(
        api_version=config.apiVersion,
        kind=config.kind,
        metadata=V1ObjectMeta(name=config.name, namespace=config.namespace, labels=config.labels),
        spec=V1ServiceSpec(
            cluster_ip=config.service_spec.cluster_ip,
            selector=config.service_spec.selector,
            ports=config.service_spec.ports,
        ),
    )
