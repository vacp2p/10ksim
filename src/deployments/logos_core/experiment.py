#!/usr/bin/env python3

import asyncio
import json
import logging
import random
import traceback
from typing import List, Literal, Optional

from kubernetes.dynamic.exceptions import ApiException
from pydantic import BaseModel, ConfigDict, NonNegativeFloat, NonNegativeInt, PrivateAttr

from src.deployments.core.configs.container import Image
from src.deployments.experiments.base_experiment import BaseExperiment
from src.deployments.logos_core.builders.nodes import NodesBuilder
from src.deployments.logos_core.builders.request_builder import LogoscorePodApiRequester
from src.deployments.pod_api_requester.configs import Target
from src.deployments.pod_api_requester.pod_api_requester import (
    PodApiApplicationError,
    PodApiError,
    pod_api_request,
    wrap_arg,
)
from src.deployments.registry import experiment
from src.deployments.waku.bridge import Bridge

logger = logging.getLogger(__name__)


class ExpConfig(BaseModel):
    num_relay_nodes: NonNegativeInt = 2
    num_messages: NonNegativeInt = 2
    delay_cold_start: NonNegativeFloat = 2
    delay_after_publish: NonNegativeFloat = 1
    num_bootstrap_nodes: NonNegativeInt = 2


_LOGOSCORE_PUBLISHER = {
    "service_name": "core-external",
    "app": "zerotenkay-core2",
}


def raise_unless_already_exists(e):
    if not hasattr(e, "api_exceptions"):
        raise e
    all_already_exist = True
    for api_exception in e.api_exceptions:
        if isinstance(api_exception, ApiException):
            if not (api_exception.status == 409 and api_exception.reason == "AlreadyExists"):
                all_already_exist = False
                break
        else:
            all_already_exist = False
            return

    if not all_already_exist:
        raise e


@experiment(name="core")
class LogosDeliveryExperiment(BaseExperiment[ExpConfig]):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    bootstrap_service: str = "core-bootstrap"
    relay_service: str = "core-relay"
    service_account_name: str = "secret-creator2"
    pod_container_name: str = "logoscore-0"  # All on shard 0. Eg. logoscore-0-0 logoscore-0-1

    _container_name: Optional[str] = PrivateAttr(default=None)

    @classmethod
    def add_parser(cls, subparsers) -> None:
        subparser = subparsers.add_parser(cls.name, help="nimlibp2p2 experiment")
        BaseExperiment.add_args(subparser)

    def _get_metadata(self) -> dict:
        metadata = Bridge().get_metadata(self.events_log_path)
        metadata["stack"]["container_name"] = self._container_name
        return metadata

    def build_publisher(self):
        builder = (
            LogoscorePodApiRequester()
            .with_namespace(self.namespace)
            .with_name("logoscore-requester")
            .with_image(Image(repo="pearsonwhite/dst-lc-api", tag="wip-amd"))
            .with_mode("server")
            .with_service_account_name(self.service_account_name)
            .with_service_name(_LOGOSCORE_PUBLISHER["service_name"])
            .with_app(_LOGOSCORE_PUBLISHER["app"])
            .with_logoscore()
            .with_dns_search(f"{self.bootstrap_service}.{self.namespace}.svc.cluster.local")
            .with_dns_search(f"{self.relay_service}.{self.namespace}.svc.cluster.local")
        )
        return {"pod": builder.build(), **builder.build_dependencies()}

    def build_node_deployments(self, type: Literal["relay", "bootstrap"]):
        if type == "relay":
            name = "relay-nodes-0"
            service = self.relay_service
            replicas = self.config.num_relay_nodes
        else:
            name = "bootstrap-nodes-0"
            service = self.bootstrap_service
            replicas = self.config.num_bootstrap_nodes
        builder = (
            NodesBuilder()
            .with_container_name(self.pod_container_name)
            .with_config(namespace=self.namespace, name=name)
            .with_service_name(service)
            .with_replicas(replicas)
            .with_dns_service([self.relay_service, self.bootstrap_service])
            .with_service_account_name(self.service_account_name)
        )
        return {"stateful_set": builder.build(), **builder.build_dependencies()}

    async def deploy_all(self, deployment, exist_ok: bool = False):
        if isinstance(deployment, dict):
            for _, dep in deployment.items():
                await self.deploy_all(dep)
        elif isinstance(deployment, list):
            for dep in deployment:
                await self.deploy_all(dep)
        else:
            try:
                await self.deploy(deployment=deployment, wait_for_ready=True)
            except Exception as e:
                # Ignore duplicate dependencies between bootstrap and relay
                raise_unless_already_exists(e)

    async def _run(self):
        self.log_event("run_start")

        publisher_deployments = self.build_publisher()
        publisher_pod = publisher_deployments["pod"]
        del publisher_deployments["pod"]
        publisher_deps = publisher_deployments
        await self.deploy_all(publisher_deps, exist_ok=False)
        await self.deploy(deployment=publisher_pod, wait_for_ready=True, exist_ok=True)

        bootstrap_deployments = self.build_node_deployments("bootstrap")
        bootstrap_ss = bootstrap_deployments["stateful_set"]
        del bootstrap_deployments["stateful_set"]
        await self.deploy_all(bootstrap_deployments, exist_ok=False)
        await self.deploy(deployment=bootstrap_ss, exist_ok=True)

        logger.info(f"Waiting for cold_start_delay: {self.config.delay_cold_start}")
        await asyncio.sleep(self.config.delay_cold_start)

        bootstrap_name = bootstrap_ss.metadata.name
        self.log_event("init_bootstrap_nodes")
        for index in range(self.config.num_bootstrap_nodes):
            indexed_name = f"{bootstrap_name}-{index}"
            try:
                await init_token(self.namespace, indexed_name, self.bootstrap_service)
            except Exception as e:
                logger.error(f"e: {e}")
            await init_node(self.namespace, indexed_name, self.bootstrap_service)

        # Get bootstrap addresses
        addresses = []
        for index in range(self.config.num_bootstrap_nodes):
            indexed_name = f"{bootstrap_name}-{index}"
            address = await get_address(self.namespace, indexed_name, self.bootstrap_service)
            addresses.append(address)
        logger.info(f"Addresses {addresses}")

        relay_deployments = self.build_node_deployments("relay")
        relay_ss = relay_deployments["stateful_set"]
        del relay_deployments["stateful_set"]
        await self.deploy_all(relay_deployments, exist_ok=False)
        await self.deploy(deployment=relay_ss, wait_for_ready=True)

        self.log_event("init_relay_nodes")
        relay_name = relay_ss.metadata.name
        for index in range(self.config.num_relay_nodes):
            indexed_name = f"{relay_name}-{index}"
            try:
                await init_token(self.namespace, indexed_name, self.relay_service)
            except Exception as e:
                logger.error(f"e: {e}")
            await init_node(self.namespace, indexed_name, self.relay_service, addresses)

        for name, service in zip(
            [bootstrap_name, relay_name], [self.bootstrap_service, self.relay_service]
        ):
            for index in range(self.config.num_relay_nodes):
                indexed_name = f"{name}-{index}"
                await start_node(self.namespace, indexed_name, service)

        topic = "/my-app/1/dst/proto"
        for index in range(self.config.num_relay_nodes):
            indexed_name = f"{relay_name}-{index}"
            await subscribe(self.namespace, indexed_name, self.relay_service, topic)

        message = "aGVsbG8="  # Test message
        for _message_index in range(self.config.num_messages):
            index = random.randrange(0, self.config.num_relay_nodes)
            indexed_name = f"{relay_name}-{index}"
            await send(self.namespace, indexed_name, self.relay_service, topic, message)

        await asyncio.sleep(20)
        self.log_event("publisher_wait_finished")
        self.log_event("internal_run_finished")


async def send(namespace, name_with_index, service_name, topic, message):
    params = {
        "module": "delivery_module",
        "function": "send",
        "params": [topic, message],
    }

    try:
        target = Target(
            name="pub",
            name_template=name_with_index,
            service=service_name,
            port=8645,
        )
        return await pod_api_request(
            namespace=namespace,
            service_name=_LOGOSCORE_PUBLISHER["service_name"],
            app=_LOGOSCORE_PUBLISHER["app"],
            url_template="http://{target_ip}:{node_port}/logoscore/call",
            data={
                "target": wrap_arg(target),
                "params": params,
            },
        )
    except PodApiApplicationError as e:
        logger.error(f"PodApiApplicationError: {e} {traceback.format_exc()}")
    except PodApiError as e:
        logger.error(f"PodApiError: {e} {traceback.format_exc()}")
    except Exception as e:
        logger.error(f"Other exception: {e} {traceback.format_exc()}")


async def subscribe(namespace, name_with_index, service_name, topic):
    params = {
        "module": "delivery_module",
        "function": "subscribe",
        "params": topic,
    }

    try:
        target = Target(
            name="pub",
            name_template=name_with_index,
            service=service_name,
            port=8645,
        )
        return await pod_api_request(
            namespace=namespace,
            service_name=_LOGOSCORE_PUBLISHER["service_name"],
            app=_LOGOSCORE_PUBLISHER["app"],
            url_template="http://{target_ip}:{node_port}/logoscore/call",
            data={
                "target": wrap_arg(target),
                "params": params,
            },
        )
    except PodApiApplicationError as e:
        logger.error(f"PodApiApplicationError: {e} {traceback.format_exc()}")
    except PodApiError as e:
        logger.error(f"PodApiError: {e} {traceback.format_exc()}")
    except Exception as e:
        logger.error(f"Other exception: {e} {traceback.format_exc()}")


async def start_node(namespace, name_with_index, service_name):
    params = {
        "module": "delivery_module",
        "function": "start",
        "params": None,
    }

    try:
        target = Target(
            name="pub",
            name_template=name_with_index,
            service=service_name,
            port=8645,
        )
        return await pod_api_request(
            namespace=namespace,
            service_name=_LOGOSCORE_PUBLISHER["service_name"],
            app=_LOGOSCORE_PUBLISHER["app"],
            url_template="http://{target_ip}:{node_port}/logoscore/call",
            data={
                "target": wrap_arg(target),
                "params": params,
            },
        )
    except PodApiApplicationError as e:
        logger.error(f"PodApiApplicationError: {e} {traceback.format_exc()}")
    except PodApiError as e:
        logger.error(f"PodApiError: {e} {traceback.format_exc()}")
    except Exception as e:
        logger.error(f"Other exception: {e} {traceback.format_exc()}")


async def init_node(
    namespace, name_with_index, service_name, entry_nodes: Optional[List[str]] = None
):
    func_params = {
        "mode": "Core",
        "clusterId": 42,
        "relay": "true",
        "tcpPort": 60000,
        "numShardsInNetwork": 8,
        "maxMessageSize": "150KiB",
        "logLevel": "INFO",
        "logFormat": "TEXT",
    }
    params = {
        "module": "delivery_module",
        "function": "createNode",
        "params": func_params,
    }
    if entry_nodes:
        func_params["entryNodes"] = entry_nodes

    try:
        target = Target(
            name="pub",
            name_template=name_with_index,
            service=service_name,
            port=8645,
        )
        return await pod_api_request(
            namespace=namespace,
            service_name=_LOGOSCORE_PUBLISHER["service_name"],
            app=_LOGOSCORE_PUBLISHER["app"],
            url_template="http://{target_ip}:{node_port}/logoscore/call",
            data={
                "target": wrap_arg(target),
                "params": params,
            },
        )
    except PodApiApplicationError as e:
        logger.error(f"PodApiApplicationError: {e} {traceback.format_exc()}")
    except PodApiError as e:
        logger.error(f"PodApiError: {e} {traceback.format_exc()}")
    except Exception as e:
        logger.error(f"Other exception: {e} {traceback.format_exc()}")


async def get_address(namespace, name_with_index, service) -> str:
    params = {
        "module": "delivery_module",
        "function": "getNodeInfo",
        "params": "MyMultiaddresses",
    }
    try:
        target = Target(
            name="pub",
            name_template=name_with_index,
            service=service,
            port=8645,
        )
        request = await pod_api_request(
            namespace=namespace,
            service_name=_LOGOSCORE_PUBLISHER["service_name"],
            app=_LOGOSCORE_PUBLISHER["app"],
            url_template="http://{target_ip}:{node_port}/logoscore/call",
            data={
                "target": wrap_arg(target),
                "params": params,
            },
        )
        response_obj = json.loads(request["response"]["text"])
        libp2p_ip = response_obj["value"]
        actual_ip = request["request"]["target"]["ip"]
        ip = libp2p_ip.replace("127.0.0.1", actual_ip)
        return ip
    except PodApiApplicationError as e:
        logger.error(f"PodApiApplicationError: {e} {traceback.format_exc()}")
    except PodApiError as e:
        logger.error(f"PodApiError: {e} {traceback.format_exc()}")
    except Exception as e:
        logger.error(f"Other exception: {e} {traceback.format_exc()}")


async def init_token(namespace, name_with_index, service_name):
    try:
        target = Target(
            name="pub",
            name_template=name_with_index,
            service=service_name,
            port=8645,
        )
        return await pod_api_request(
            namespace=namespace,
            service_name=_LOGOSCORE_PUBLISHER["service_name"],
            app=_LOGOSCORE_PUBLISHER["app"],
            url_template="http://{target_ip}:{node_port}/logoscore/init",
            data={
                "target": wrap_arg(target),
            },
        )
    except PodApiApplicationError as e:
        logger.error(f"PodApiApplicationError: {e} {traceback.format_exc()}")
    except PodApiError as e:
        logger.error(f"PodApiError: {e} {traceback.format_exc()}")
    except Exception as e:
        logger.error(f"Other exception: {e} {traceback.format_exc()}")
