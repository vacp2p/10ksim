# Python Imports
from typing import List

from kubernetes.client import V1ContainerPort, V1PodDNSConfig, V1ResourceRequirements

# Project Imports
from src.deployments.core.configs.container import ContainerConfig, Image
from src.deployments.core.configs.pod import PodSpecConfig, PodTemplateSpecConfig
from src.deployments.core.configs.statefulset import StatefulSetSpecConfig
from src.deployments.libp2p.builders.helpers import LIBP2P_CONTAINER_NAME


class Nodes:
    """Base configuration for libp2p nodes."""

    DEFAULT_NAMESPACE = "zerotesting-nimlibp2p"
    DEFAULT_SERVICE_NAME = "nimp2p-service"
    DEFAULT_IMAGE = Image(repo="pearsonwhite/dst-nimlibp2p-logging", tag="v3")

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
        dns_searches: List[str],
        namespace: str,
    ) -> PodSpecConfig:
        dns_config = None
        if dns_searches:
            dns_searches_complete = [
                f"{service}.{namespace}.svc.cluster.local" for service in dns_searches
            ]
            dns_config = V1PodDNSConfig(searches=dns_searches_complete)

        return PodSpecConfig(
            container_configs=[Nodes.create_container_config()],
            dns_config=dns_config,
        )

    @staticmethod
    def create_pod_template_spec_config(
        dns_searches: List[str],
        namespace: str,
    ) -> PodTemplateSpecConfig:
        config = PodTemplateSpecConfig(
            pod_spec_config=Nodes.create_pod_spec_config(dns_searches, namespace)
        )
        config.with_app("zerotenkay")
        return config

    @staticmethod
    def create_stateful_set_spec_config(
        service: str,
        namespace: str,
        dns_searches: List[str],
    ) -> StatefulSetSpecConfig:
        config = StatefulSetSpecConfig(
            replicas=0,
            service_name=service,
            pod_template_spec_config=Nodes.create_pod_template_spec_config(dns_searches, namespace),
        )
        config.with_app("zerotenkay")
        return config
