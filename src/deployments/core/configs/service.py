from typing import Dict, List, Literal, Optional, Self

from kubernetes.client import V1ObjectMeta, V1Service, V1ServicePort, V1ServiceSpec
from pydantic import BaseModel, ConfigDict, Field

ServiceSpecType = Literal["ClusterIP", "NodePort", "LoadBalancer", "ExternalName"]


class ServiceSpecConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    spec_type: Optional[ServiceSpecType] = None
    cluster_ip: Optional[str] = None
    selector: Optional[Dict[str, str]] = None
    ports: Optional[List[V1ServicePort]] = None
    publish_not_ready_addresses: Optional[bool] = None

    def with_selector(self, key: str, value: str):
        if self.selector is None:
            self.selector = {}
        self.selector[key] = value

    def with_port(self, new_port: V1ServicePort, overwrite: bool = False):
        if self.ports is None:
            self.ports = []

        current_port = next((item for item in self.ports if item == new_port), None)
        if current_port:
            if not overwrite:
                raise ValueError(
                    f"Port already exists in {type(self).__name__}. "
                    f"Port: `{new_port.port}`, Protocol: `{getattr(new_port, 'protocol', 'TCP')}`, "
                    f"Config: `{self}`"
                )
            self.ports.remove(current_port)

        self.ports.append(new_port)
        return self


class ServiceConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: Optional[str] = None
    namespace: Optional[str] = None
    apiVersion: Optional[str] = Field(default="v1")
    kind: Optional[str] = Field(default="Service")
    labels: Optional[Dict[str, str]] = None
    service_spec: ServiceSpecConfig = Field(default_factory=ServiceSpecConfig)


class ServiceConfigBuilder(BaseModel):
    config: ServiceConfig = Field(default_factory=ServiceConfig)

    def with_port(self, new_port: V1ServicePort) -> Self:
        self.service_spec.with_port(new_port)
        return self

    def with_type(self, spec_type: ServiceSpecType) -> Self:
        self.service_spec.spec_type = spec_type
        return self

    def build(self) -> V1Service:
        return build_service(self.config)


def build_service(config: ServiceConfig) -> V1Service:
    return V1Service(
        api_version=config.apiVersion,
        kind=config.kind,
        metadata=V1ObjectMeta(name=config.name, namespace=config.namespace, labels=config.labels),
        spec=V1ServiceSpec(
            type=config.service_spec.spec_type,
            cluster_ip=config.service_spec.cluster_ip,
            selector=config.service_spec.selector,
            ports=config.service_spec.ports,
            publish_not_ready_addresses=config.service_spec.publish_not_ready_addresses,
        ),
    )
