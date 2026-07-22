# Python Imports
import asyncio
import logging
from typing import ClassVar, List

from kubernetes.client import V1Probe, V1ServicePort, V1StatefulSet, V1TCPSocketAction
from pydantic import BaseModel, ConfigDict, NonNegativeInt

# Project Imports
from src.deployments.core.builders import ServiceBuilder
from src.deployments.core.configs.container import Image
from src.deployments.experiments.base_experiment import BaseExperiment
from src.deployments.libp2p.builders.builders import Libp2pStatefulSetBuilder
from src.deployments.libp2p.service_discovery_bridge import ServiceDiscoveryBridge
from src.deployments.registry import experiment

logger = logging.getLogger(__name__)

READINESS_PROBE = V1Probe(
    tcp_socket=V1TCPSocketAction(port=8645),
    initial_delay_seconds=2,
    period_seconds=5,
)


class ExpConfig(BaseModel):
    model_config = ConfigDict(extra="ignore") # TODO Para que es esto

    # Bootstrap
    num_bootstraps: NonNegativeInt = 1
    bootstrap_ss_name: str = "bootstrap"
    bootstrap_service_name: str = "bootstrap-service"
    bootstrap_role: str = "bootstrap"
    bootstrap_service_port: int = 5000

    # Popular Advertisers
    num_popular_advertisers: NonNegativeInt = 5
    popular_advertisers_ss_name: str = "popular-advertiser"
    advertisers_service_name: str = "advertisers-service"
    popular_advertiser_role: str = "popular-advertiser"
    popular_service_port: int = 5000

    # Rare Advertisers
    num_rare_advertisers: NonNegativeInt = 1
    rare_advertisers_ss_name: str = "rare-advertiser"
    rare_advertiser_role: str = "rare-advertiser"

    # Popular Discoverers
    num_discoverer: NonNegativeInt = 1
    popular_discoverer_ss_name: str = "popular-discoverer"
    popular_discoverer_role: str = "popular-discoverer"

    # Rare Discoverers
    num_discoverer_rare: NonNegativeInt = 1
    rare_discoverer_ss_name: str = "rare-discoverer"
    rare_discoverer_role: str = "rare-discoverer"

    # General
    image_repo: str = "soutullostatus/service-discovery"
    image_tag: str = "v2.0.0"
    namespace: str = "nimlibp2p"
    dns_searches: List[str] = [bootstrap_service_name, advertisers_service_name]

    app_name: str = "service-discovery"


@experiment(name="service-discovery")
class ServiceDiscovery(BaseExperiment[ExpConfig]):
    """Service discovery experiment"""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    post_run_analysis: ClassVar[str] = (
        "src.analysis.post_run.service_discovery:run_service_discovery_analysis"
    )

    def _get_metadata(self) -> dict:
        return ServiceDiscoveryBridge().get_metadata(self.events_log_path)

    def log_event(self, event):
        logger.info(event)
        return super().log_event(event)

    async def _deploy_bootstrap(self, image: Image):
        bootstrap_service = (
            ServiceBuilder()
            .with_name(self.config.bootstrap_service_name)
            .with_namespace(self.config.namespace)
            .with_selector("app", self.config.app_name)
            .with_selector("role", self.config.bootstrap_role)
            .with_port(
                V1ServicePort(
                    port=self.config.bootstrap_service_port,
                    target_port=self.config.bootstrap_service_port,
                )
            )
            .with_cluster_ip("None")
            .build()
        )
        await self.deploy(deployment=bootstrap_service)
        self.log_event("Bootstrap service deployed")

        bootstrap = (
            Libp2pStatefulSetBuilder()
            .with_libp2p_config(
                name=self.config.bootstrap_ss_name,
                namespace=self.config.namespace,
                num_nodes=self.config.num_bootstraps,
                service=self.config.bootstrap_service_name,
            )
            .with_readiness_probe(READINESS_PROBE)
            .with_image(image)
            .with_option("NODE_ROLE", "RoleBootstrap")
            .with_option("MAXCONNECTIONS", "1000")
            .with_pull_policy("IfNotPresent")
            .with_label("app", self.config.app_name)
            .with_label("role", self.config.bootstrap_role)
            .build()
        )

        await self.deploy(deployment=bootstrap, wait_for_ready=True)
        self.log_event("Bootstrap nodes deployed")

    async def _deploy_popular_advertisers(self, image: Image):
        popular_advertisers_service = (
            ServiceBuilder()
            .with_name(self.config.advertisers_service_name)
            .with_namespace(self.config.namespace)
            .with_selector("app", self.config.app_name)
            .with_selector("role", self.config.popular_advertiser_role)
            .with_port(
                V1ServicePort(
                    port=self.config.popular_service_port,
                    target_port=self.config.popular_service_port,
                )
            )
            .with_cluster_ip("None")
            .build()
        )
        await self.deploy(deployment=popular_advertisers_service)
        self.log_event("Popular advertisers service deployed")

        popular_advertisers = (
            Libp2pStatefulSetBuilder()
            .with_libp2p_config(
                name=self.config.popular_advertisers_ss_name,
                namespace=self.config.namespace,
                num_nodes=self.config.num_popular_advertisers,
                dns_searches=self.config.dns_searches,
                service=self.config.advertisers_service_name,
            )
            .with_readiness_probe(READINESS_PROBE)
            .with_image(image)
            .with_option("NODE_ROLE", "RoleAdvertiser")
            .with_option("SERVICE", self.config.bootstrap_service_name)
            .with_option("ADVERTISE_SERVICES", "chat1,chat2,chat3")
            .with_option("MAXCONNECTIONS", "1000")
            .with_pull_policy("IfNotPresent")
            .with_label("app", self.config.app_name)
            .with_label("role", self.config.popular_advertiser_role)
            .build()
        )

        await self.deploy(deployment=popular_advertisers, wait_for_ready=True)
        self.log_event("popular_advertisers deployed")

    async def _deploy_rare_advertiser(self, image: Image):
        rare_advertisers = (
            Libp2pStatefulSetBuilder()
            .with_libp2p_config(
                name=self.config.rare_advertisers_ss_name,
                namespace=self.config.namespace,
                num_nodes=self.config.num_rare_advertisers,
                service=self.config.advertisers_service_name,
                dns_searches=self.config.dns_searches,
            )
            .with_readiness_probe(READINESS_PROBE)
            .with_image(image)
            .with_option("NODE_ROLE", "RoleAdvertiser")
            .with_option("SERVICE", self.config.advertisers_service_name)
            .with_option("ADVERTISE_SERVICES", "secret_chat")
            .with_pull_policy("IfNotPresent")
            .with_label("app", self.config.app_name)
            .with_label("role", self.config.rare_advertiser_role)
            .build()
        )

        await self.deploy(deployment=rare_advertisers, wait_for_ready=True)
        self.log_event("rare_advertisers deployed")

    async def _deploy_popular_discoverer(self, image: Image):
        discoverer = (
            Libp2pStatefulSetBuilder()
            .with_libp2p_config(
                name=self.config.popular_discoverer_ss_name,
                namespace=self.config.namespace,
                num_nodes=self.config.num_discoverer,
                service=self.config.advertisers_service_name,
                dns_searches=self.config.dns_searches,
            )
            .with_readiness_probe(READINESS_PROBE)
            .with_image(image)
            .with_option("NODE_ROLE", "RoleDiscoverer")
            .with_option("SERVICE", self.config.advertisers_service_name)
            .with_option("DISCOVER_SERVICES", "chat1")
            .with_option("MAXBOOTSTRAPS", 1)
            .with_pull_policy("IfNotPresent")
            .with_label("app", self.config.app_name)
            .with_label("role", self.config.popular_discoverer_role)
            .build()
        )

        await self.deploy(deployment=discoverer, wait_for_ready=True)
        self.log_event("popular discoverer deployed")

    async def _deploy_rare_discoverer(self, image: Image) -> V1StatefulSet:
        rare_discoverer = (
            Libp2pStatefulSetBuilder()
            .with_libp2p_config(
                name=self.config.rare_discoverer_ss_name,
                namespace=self.config.namespace,
                num_nodes=self.config.num_discoverer_rare,
                dns_searches=self.config.dns_searches,
            )
            .with_readiness_probe(READINESS_PROBE)
            .with_image(image)
            .with_option("NODE_ROLE", "RoleDiscoverer")
            .with_option("SERVICE", self.config.advertisers_service_name)
            .with_option("DISCOVER_SERVICES", "secret_chat")
            .with_option("MAXBOOTSTRAPS", 1)
            .with_pull_policy("Always")
            .with_label("app", self.config.app_name)
            .with_label("role", self.config.rare_discoverer_role)
            .build()
        )

        await self.deploy(deployment=rare_discoverer, wait_for_ready=True)
        self.log_event("rare_discoverer deployed")

        return rare_discoverer

    async def _run(
        self,
    ):
        self.log_event("run_start")

        image = Image(repo=self.config.image_repo, tag=self.config.image_tag)

        await self._deploy_bootstrap(image)
        await self._deploy_popular_advertisers(image)
        await self._deploy_rare_advertiser(image)
        await self._deploy_popular_discoverer(image)
        self.log_event("service_discovery_started")
        await self._deploy_rare_discoverer(image)
        # for i in range(1):
        #    rare_discoverer = await self._deploy_rare_discoverer(image)
        #    self.log_event("rare_discoverer deployed")
        #    await asyncio.sleep(60)
        #    clean = get_cleanup(self.api_client, self.config.namespace, [rare_discoverer.to_dict()])
        #    clean()

        #    self.log_event("rare_discoverer cleaned")
        await asyncio.sleep(60)
        self.log_event("service_discovery_finished")
