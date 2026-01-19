from kubernetes.client import V1ContainerPort, V1PodDNSConfig, V1ResourceRequirements

from core.configs.container import ContainerConfig, Image
from core.configs.pod import PodSpecConfig, PodTemplateSpecConfig
from core.configs.statefulset import StatefulSetConfig, StatefulSetSpecConfig
from libp2p.builders.helpers import LIBP2P_CONTAINER_NAME


class Nodes:
    """Base configuration for libp2p nodes."""

    DEFAULT_NAMESPACE = "zerotesting-nimlibp2p"
    DEFAULT_SERVICE_NAME = "nimp2p-service"
    DEFAULT_IMAGE = Image(repo="ufarooqstatus/refactored-test-node", tag="v1.0")

    @staticmethod
    def create_container_config() -> ContainerConfig:
        config = ContainerConfig(
            name=LIBP2P_CONTAINER_NAME,
            image=Nodes.DEFAULT_IMAGE,
            image_pull_policy="IfNotPresent",
        )

        config.ports = [
            V1ContainerPort(container_port=5000),
            V1ContainerPort(container_port=8008),
            V1ContainerPort(container_port=8645),
        ]

        config.with_resources(Nodes.create_resources())

        return config

    @staticmethod
    def create_resources() -> V1ResourceRequirements:
        return V1ResourceRequirements(
            requests={"memory": "64Mi", "cpu": "150m"},
            limits={"memory": "600Mi", "cpu": "400m"},
        )

    @staticmethod
    def create_pod_spec_config(
        namespace: str,
    ) -> PodSpecConfig:
        return PodSpecConfig(
            container_configs=[Nodes.create_container_config()],
            dns_config=V1PodDNSConfig(searches=[f"nimp2p-service.{namespace}.svc.cluster.local"]),
        )

    @staticmethod
    def create_pod_template_spec_config(
        namespace: str,
    ) -> PodTemplateSpecConfig:
        config = PodTemplateSpecConfig(pod_spec_config=Nodes.create_pod_spec_config(namespace))
        config.with_app("zerotenkay")
        return config

    @staticmethod
    def create_stateful_set_spec_config(
        namespace: str,
    ) -> StatefulSetSpecConfig:
        config = StatefulSetSpecConfig(
            replicas=0,
            service_name="nimp2p-service",
            pod_template_spec_config=Nodes.create_pod_template_spec_config(namespace),
        )
        config.with_app("zerotenkay")
        return config

    @staticmethod
    def create_statefulset_config(namespace: str) -> StatefulSetConfig:
        return StatefulSetConfig(
            name="pod",
            namespace=namespace,
            apiVersion="apps/v1",
            kind="StatefulSet",
            pod_management_policy="Parallel",
            stateful_set_spec=Nodes.create_stateful_set_spec_config(namespace),
        )
