# Python Imports
import logging
from typing import List

from kubernetes.client import V1Probe, V1ServicePort, V1TCPSocketAction
from pydantic import BaseModel, ConfigDict, NonNegativeInt

# Project Imports
from src.deployments.core.builders import ServiceBuilder
from src.deployments.core.configs.container import Image
from src.deployments.experiments.base_experiment import BaseExperiment
from src.deployments.libp2p.builders.builders import Libp2pStatefulSetBuilder
from src.deployments.registry import experiment

logger = logging.getLogger(__name__)

READINESS_PROBE = V1Probe(
    tcp_socket=V1TCPSocketAction(port=8645),
    initial_delay_seconds=2,
    period_seconds=5,
)


class ExpConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    num_registrars: NonNegativeInt = 10
    num_bootstraps: NonNegativeInt = 3
    image_repo: str = "soutullostatus/nimlibp2p"
    image_tag: str = "service-discovery"
    namespace: str = "nimlibp2p"
    bootstrap_service_name: str = "bootstrap-service"
    registrar_service_name: str = "registrar-service"
    kad_service_name: str = "kad-service"
    dns_searches: List[str] = ["bootstrap-service"]


@experiment(name="service-discovery")
class ServiceDiscovery(BaseExperiment[ExpConfig]):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    @classmethod
    def add_parser(cls, subparsers) -> None:
        subparser = subparsers.add_parser(cls.name, help="Connection manager experiment")
        BaseExperiment.add_args(subparser)
        subparser.set_defaults(namespace="nimlibp2p")

    def log_event(self, event):
        logger.info(event)
        return super().log_event(event)

    async def _run(
        self,
    ):
        self.log_event("run_start")

        image = Image(repo=self.config.image_repo, tag=self.config.image_tag)

        bootstrap_service = (
            ServiceBuilder()
            .with_name(self.config.bootstrap_service_name)
            .with_namespace(self.config.namespace)
            .with_selector("app", "service-discovery")
            .with_selector("role", "bootstrap")
            .with_port(V1ServicePort(port=5000, target_port=5000))
            .with_cluster_ip("None")
            .build()
        )
        self.dump_yaml(bootstrap_service, self.config.bootstrap_service_name)
        await self.deploy(deployment=bootstrap_service)
        self.log_event("Bootstrap service deployed")

        bootstrap = (
            Libp2pStatefulSetBuilder()
            .with_libp2p_config(
                name="bootstrap",
                namespace=self.config.namespace,
                num_nodes=self.config.num_bootstraps,
                service=self.config.bootstrap_service_name,
            )
            .with_readiness_probe(READINESS_PROBE)
            .with_image(image)
            .with_option("NODE_ROLE", "RoleBootstrap")
            .with_pull_policy("Always")
            .with_label("app", "service-discovery")
            .with_label("role", "bootstrap")
            .build()
        )  # TODO: Change policy

        self.dump_yaml(bootstrap, "bootstrap")
        await self.deploy(deployment=bootstrap, wait_for_ready=True)
        self.log_event("Bootstrap nodes deployed")

        registrars = (
            Libp2pStatefulSetBuilder()
            .with_libp2p_config(
                name="registrar",
                namespace=self.config.namespace,
                num_nodes=self.config.num_registrars,
                service=self.config.registrar_service_name,
                dns_searches=self.config.dns_searches,
            )
            .with_readiness_probe(READINESS_PROBE)
            .with_image(image)
            .with_option("NODE_ROLE", "RoleHybrid")
            .with_option("SERVICE", self.config.bootstrap_service_name)
            .with_option("ADVERTISE_SERVICES", "chat")
            .with_option("DISCOVER_SERVICES", "chat")
            .with_pull_policy("Always")
            .with_label("app", "service-discovery")
            .with_label("role", "registrar")
            .build()
        )  # TODO: Change policy

        self.dump_yaml(registrars, "registrars")
        await self.deploy(deployment=registrars, wait_for_ready=True)
        self.log_event("Registrar deployed")

        kad_dhts = (
            Libp2pStatefulSetBuilder()
            .with_libp2p_config(
                name="normal-kad-dht",
                namespace=self.config.namespace,
                num_nodes=self.config.num_registrars,
                service=self.config.kad_service_name,
                dns_searches=self.config.dns_searches,
            )
            .with_readiness_probe(READINESS_PROBE)
            .with_image(image)  # TODO change image
            .with_option("NODE_ROLE", "RoleBootstrap")
            .with_option("SERVICE", self.config.bootstrap_service_name)
            .with_pull_policy("Always")
            .with_label("app", "service-discovery")
            .with_label("role", "kad-dht")
            .build()
        )  # TODO: Change policy

        self.dump_yaml(kad_dhts, "kad_dhts")
        await self.deploy(deployment=kad_dhts, wait_for_ready=True)
        self.log_event("kad_dhts deployed")

        popular_advertisers = (
            Libp2pStatefulSetBuilder()
            .with_libp2p_config(
                name="popular-advertisers",
                namespace=self.config.namespace,
                num_nodes=self.config.num_registrars,
                service=self.config.registrar_service_name,
                dns_searches=self.config.dns_searches,
            )
            .with_readiness_probe(READINESS_PROBE)
            .with_image(image)
            .with_option("NODE_ROLE", "RoleAdvertiser")
            .with_option("SERVICE", self.config.bootstrap_service_name)
            .with_option("ADVERTISE_SERVICES", "chat")
            .with_pull_policy("Always")
            .with_label("app", "service-discovery")
            .with_label("role", "popular-advertiser")
            .build()
        )  # TODO: Change policy

        self.dump_yaml(registrars, "popular_advertisers")
        await self.deploy(deployment=popular_advertisers, wait_for_ready=True)
        self.log_event("popular_advertisers deployed")

        rare_advertisers = (
            Libp2pStatefulSetBuilder()
            .with_libp2p_config(
                name="rare-advertisers",
                namespace=self.config.namespace,
                num_nodes=self.config.num_registrars,
                service=self.config.registrar_service_name,
                dns_searches=self.config.dns_searches,
            )
            .with_readiness_probe(READINESS_PROBE)
            .with_image(image)
            .with_option("NODE_ROLE", "RoleAdvertiser")
            .with_option("SERVICE", self.config.bootstrap_service_name)
            .with_option("ADVERTISE_SERVICES", "secret_chat")
            .with_pull_policy("Always")
            .with_label("app", "service-discovery")
            .with_label("role", "rare-advertiser")
            .build()
        )  # TODO: Change policy

        self.dump_yaml(registrars, "rare_advertisers")
        await self.deploy(deployment=rare_advertisers, wait_for_ready=True)
        self.log_event("rare_advertisers deployed")

        discoverer = (
            Libp2pStatefulSetBuilder()
            .with_libp2p_config(
                name="discoverer",
                namespace=self.config.namespace,
                num_nodes=self.config.num_registrars,
                service=self.config.registrar_service_name,
                dns_searches=self.config.dns_searches,
            )
            .with_readiness_probe(READINESS_PROBE)
            .with_image(image)
            .with_option("NODE_ROLE", "RoleDiscoverer")
            .with_option("SERVICE", self.config.bootstrap_service_name)
            .with_option("DISCOVER_SERVICES", "secret_chat")
            .with_pull_policy("Always")
            .with_label("app", "service-discovery")
            .with_label("role", "rare-advertiser")
            .build()
        )  # TODO: Change policy

        self.dump_yaml(registrars, "discoverer")
        await self.deploy(deployment=discoverer, wait_for_ready=True)
        self.log_event("discoverer deployed")
