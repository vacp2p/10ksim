# Python Imports
import logging
from argparse import Namespace
from contextlib import ExitStack
from typing import List, Optional

from kubernetes.client import ApiClient, V1Probe, V1ServicePort, V1TCPSocketAction
from pydantic import BaseModel, ConfigDict, NonNegativeInt
from ruamel import yaml

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


# TODO: Check namespace is already created when we deploy.
# TODO: Utilities to set up resources and that stuff should be located in same place (shared between builders)
# TODO: How do we handle different containers in the same pod? Should be more direct
# TODO: Why do we need namespace in subparser and ExperimentConfig also
# TODO: Reduce log levels


@experiment(name="service-discovery")
class ServiceDiscovery(BaseExperiment, BaseModel):

    @classmethod
    def add_parser(cls, subparsers) -> None:
        subparser = subparsers.add_parser(cls.name, help="Connection manager experiment")
        BaseExperiment.add_args(subparser)
        subparser.set_defaults(namespace="nimlibp2p")

    def log_event(self, event):  # TODO deberia ser de base experiment??
        logger.info(event)
        return super().log_event(event)

    async def _run(
        self,
        api_client: ApiClient,
        workdir: str,
        args: Namespace,
        values_yaml: Optional[yaml.YAMLObject],
        stack: ExitStack,
    ):
        pass

    model_config = ConfigDict(arbitrary_types_allowed=True)

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

    async def _run(
        self,
        api_client: ApiClient,
        workdir: str,
        args: Namespace,
        values_yaml: Optional[dict],
        stack: ExitStack,
    ):
        # Rare Service Discovery in a Large Noisy Network
        # https://www.notion.so/Dogfooding-Service-Discovery-3528f96fb65c800f98d2f1bbaf1822f1?source=copy_link#35d8f96fb65c80bf9200fc87374b5044
        self.log_event("run_start")
        config = self.ExpConfig(**values_yaml)
        self.log_metadata({"params": vars(config)})

        image = Image(repo=config.image_repo, tag=config.image_tag)

        bootstrap_service = (
            ServiceBuilder()
            .with_name(config.bootstrap_service_name)
            .with_namespace(config.namespace)
            .with_selector("app", "service-discovery")
            .with_selector("role", "bootstrap")
            .with_port(V1ServicePort(port=5000, target_port=5000))
            .with_cluster_ip("None")
            .build()
        )
        self.dump_yaml(bootstrap_service, workdir, config.bootstrap_service_name)
        await self.deploy(api_client, stack, args, {}, deployment=bootstrap_service)
        self.log_event("Bootstrap service deployed")

        bootstrap = (
            Libp2pStatefulSetBuilder()
            .with_libp2p_config(
                name="bootstrap",
                namespace=config.namespace,
                num_nodes=config.num_bootstraps,
                service=config.bootstrap_service_name,
            )
            .with_readiness_probe(READINESS_PROBE)
            .with_image(image)
            .with_option("NODE_ROLE", "RoleBootstrap")
            .with_pull_policy("Always")
            .with_label("app", "service-discovery")
            .with_label("role", "bootstrap")
            .build()
        )  # TODO: Change policy

        self.dump_yaml(bootstrap, workdir, "bootstrap")
        await self.deploy(api_client, stack, args, {}, deployment=bootstrap, wait_for_ready=True)
        self.log_event("Bootstrap nodes deployed")

        registrars = (
            Libp2pStatefulSetBuilder()
            .with_libp2p_config(
                name="registrar",
                namespace=config.namespace,
                num_nodes=config.num_registrars,
                service=config.registrar_service_name,
                dns_searches=config.dns_searches,
            )
            .with_readiness_probe(READINESS_PROBE)
            .with_image(image)
            .with_option("NODE_ROLE", "RoleHybrid")
            .with_option("SERVICE", config.bootstrap_service_name)
            .with_option("ADVERTISE_SERVICES", "chat")
            .with_option("DISCOVER_SERVICES", "chat")
            .with_pull_policy("Always")
            .with_label("app", "service-discovery")
            .with_label("role", "registrar")
            .build()
        )  # TODO: Change policy

        self.dump_yaml(registrars, workdir, "registrars")
        await self.deploy(api_client, stack, args, {}, deployment=registrars, wait_for_ready=True)
        self.log_event("Registrar deployed")

        kad_dhts = (
            Libp2pStatefulSetBuilder()
            .with_libp2p_config(
                name="normal-kad-dht",
                namespace=config.namespace,
                num_nodes=config.num_registrars,
                service=config.kad_service_name,
                dns_searches=config.dns_searches,
            )
            .with_readiness_probe(READINESS_PROBE)
            .with_image(image)  # TODO change image
            .with_option("NODE_ROLE", "RoleBootstrap")
            .with_option("SERVICE", config.bootstrap_service_name)
            .with_pull_policy("Always")
            .with_label("app", "service-discovery")
            .with_label("role", "kad-dht")
            .build()
        )  # TODO: Change policy

        self.dump_yaml(kad_dhts, workdir, "kad_dhts")
        await self.deploy(api_client, stack, args, {}, deployment=kad_dhts, wait_for_ready=True)
        self.log_event("kad_dhts deployed")

        popular_advertisers = (
            Libp2pStatefulSetBuilder()
            .with_libp2p_config(
                name="popular-advertisers",
                namespace=config.namespace,
                num_nodes=config.num_registrars,
                service=config.registrar_service_name,
                dns_searches=config.dns_searches,
            )
            .with_readiness_probe(READINESS_PROBE)
            .with_image(image)
            .with_option("NODE_ROLE", "RoleAdvertiser")
            .with_option("SERVICE", config.bootstrap_service_name)
            .with_option("ADVERTISE_SERVICES", "chat")
            .with_pull_policy("Always")
            .with_label("app", "service-discovery")
            .with_label("role", "popular-advertiser")
            .build()
        )  # TODO: Change policy

        self.dump_yaml(registrars, workdir, "popular_advertisers")
        await self.deploy(
            api_client, stack, args, {}, deployment=popular_advertisers, wait_for_ready=True
        )
        self.log_event("popular_advertisers deployed")

        rare_advertisers = (
            Libp2pStatefulSetBuilder()
            .with_libp2p_config(
                name="popular-advertisers",
                namespace=config.namespace,
                num_nodes=config.num_registrars,
                service=config.registrar_service_name,
                dns_searches=config.dns_searches,
            )
            .with_readiness_probe(READINESS_PROBE)
            .with_image(image)
            .with_option("NODE_ROLE", "RoleAdvertiser")
            .with_option("SERVICE", config.bootstrap_service_name)
            .with_option("ADVERTISE_SERVICES", "secret_chat")
            .with_pull_policy("Always")
            .with_label("app", "service-discovery")
            .with_label("role", "rare-advertiser")
            .build()
        )  # TODO: Change policy

        self.dump_yaml(registrars, workdir, "rare_advertisers")
        await self.deploy(
            api_client, stack, args, {}, deployment=rare_advertisers, wait_for_ready=True
        )
        self.log_event("rare_advertisers deployed")

        discoverer = (
            Libp2pStatefulSetBuilder()
            .with_libp2p_config(
                name="popular-advertisers",
                namespace=config.namespace,
                num_nodes=config.num_registrars,
                service=config.registrar_service_name,
                dns_searches=config.dns_searches,
            )
            .with_readiness_probe(READINESS_PROBE)
            .with_image(image)
            .with_option("NODE_ROLE", "RoleDiscoverer")
            .with_option("SERVICE", config.bootstrap_service_name)
            .with_option("DISCOVER_SERVICES", "secret_chat")
            .with_pull_policy("Always")
            .with_label("app", "service-discovery")
            .with_label("role", "rare-advertiser")
            .build()
        )  # TODO: Change policy

        self.dump_yaml(registrars, workdir, "discoverer")
        await self.deploy(api_client, stack, args, {}, deployment=discoverer, wait_for_ready=True)
        self.log_event("discoverer deployed")
