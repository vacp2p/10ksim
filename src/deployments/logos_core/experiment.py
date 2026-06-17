#!/usr/bin/env python3

import asyncio
import json
import logging
import traceback
from typing import List, Optional

from kubernetes.dynamic.exceptions import ApiException
from pydantic import BaseModel, ConfigDict, NonNegativeFloat, NonNegativeInt

from src.deployments.core.configs.container import Image
from src.deployments.experiments.base_experiment import BaseExperiment
from src.deployments.libp2p.bridge import Bridge
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

logger = logging.getLogger(__name__)


class ExpConfig(BaseModel):
    num_nodes: NonNegativeInt = 2
    num_messages: NonNegativeInt = 20
    delay_cold_start: NonNegativeFloat = 2
    delay_after_publish: NonNegativeFloat = 1


_LOGOSCORE_PUBLISHER = {
    "service_name": "core-external",
    "app": "zerotenkay-core2",
}


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

    @classmethod
    def add_parser(cls, subparsers) -> None:
        subparser = subparsers.add_parser(cls.name, help="nimlibp2p2 experiment")
        BaseExperiment.add_args(subparser)

    def _get_metadata(self) -> dict:
        return Bridge().get_metadata(self.events_log_path)

    async def _run(self):
        self.log_event("run_start")
        bootstrap_service = "core-bootstrap"
        relay_service = "core-relay"
        service_account_name = "secret-creator2"

        publisher_builder = (
            LogoscorePodApiRequester()
            .with_namespace(self.namespace)
            .with_image(Image(repo="pearsonwhite/dst-lc-api", tag="wip-amd"))
            .with_mode("server")
            .with_service_account_name(service_account_name)
            .with_service_name(_LOGOSCORE_PUBLISHER["service_name"])
            .with_logoscore_profile(
                self.namespace, name="logoscore-requester", app=_LOGOSCORE_PUBLISHER["app"]
            )
            .with_dns_search(f"{bootstrap_service}.{self.namespace}.svc.cluster.local")
            .with_dns_search(f"{relay_service}.{self.namespace}.svc.cluster.local")
        )

        dependencies = publisher_builder.build_dependencies()
        for _name, dep_list in dependencies.items():
            for dep in dep_list:
                logger.info(f"Deploying dependency: {_name}")
                logger.info(f"{dep.metadata.namespace}")
                logger.info(f"{dep.metadata.name}")
                logger.info(f"{type(dep.metadata)}")
                await self.deploy(deployment=dep, wait_for_ready=True)

        await self.deploy(deployment=publisher_builder.build(), wait_for_ready=True)

        bootstrap_nodes_builder = (
            NodesBuilder()
            .with_config(namespace=self.namespace, name="bootstrap-nodes")
            .with_service_name(bootstrap_service)
            .with_replicas(self.config.num_nodes)
            .with_dns_service([relay_service, bootstrap_service])
            .with_service_account_name(service_account_name)
        )
        nodes_deps = bootstrap_nodes_builder.build_dependencies()
        for _kind, deps in nodes_deps.items():
            for dep in deps:
                try:
                    await self.deploy(deployment=dep, wait_for_ready=True)
                except Exception as e:
                    # Ignore duplicate dependencies between bootstrap and relay
                    raise_unless_already_exists(e)
        bootstrap_nodes = bootstrap_nodes_builder.build()
        await self.deploy(deployment=bootstrap_nodes, wait_for_ready=True)

        logger.info(f"Waiting for cold_start_delay: {self.config.delay_cold_start}")
        await asyncio.sleep(self.config.delay_cold_start)

        bootstrap_name = bootstrap_nodes.metadata.name
        self.log_event("init_bootstrap_nodes")
        for index in range(self.config.num_nodes):
            indexed_name = f"{bootstrap_name}-{index}"
            try:
                await init_token(self.namespace, indexed_name, bootstrap_service)
            except Exception as e:
                logger.error(f"e: {e}")
            await init_node(self.namespace, indexed_name, bootstrap_service)

        # Get bootstrap ENRs
        addresses = []
        for index in range(self.config.num_nodes):
            indexed_name = f"{bootstrap_name}-{index}"
            address = await get_address(self.namespace, indexed_name, bootstrap_service)
            addresses.append(address)
        logger.info(f"Addresses {addresses}")

        relay_nodes_builder = (
            NodesBuilder()
            .with_config(namespace=self.namespace)
            .with_service_name(relay_service)
            .with_replicas(self.config.num_nodes)
            .with_dns_service([relay_service, bootstrap_service])
            .with_service_account_name(service_account_name)
        )
        nodes_deps = relay_nodes_builder.build_dependencies()
        for _kind, deps in nodes_deps.items():
            for dep in deps:
                try:
                    await self.deploy(deployment=dep, wait_for_ready=True)
                except Exception as e:
                    # Ignore duplicate dependencies between bootstrap and relay
                    raise_unless_already_exists(e)

        self.log_event("init_relay_nodes")
        relay_nodes = relay_nodes_builder.build()
        relay_name = relay_nodes.metadata.name
        await self.deploy(deployment=relay_nodes, wait_for_ready=True)
        for index in range(self.config.num_nodes):
            indexed_name = f"{relay_name}-{index}"
            try:
                await init_token(self.namespace, indexed_name, relay_service)
            except Exception as e:
                logger.error(f"e: {e}")
            await init_node(self.namespace, indexed_name, relay_service, addresses)

        for name, service in zip([bootstrap_name, relay_name], [bootstrap_service, relay_service]):
            for index in range(self.config.num_nodes):
                indexed_name = f"{name}-{index}"
                await start_node(self.namespace, indexed_name, service)

        topic = "/my-app/1/dst/proto"
        for index in range(self.config.num_nodes):
            indexed_name = f"{relay_name}-{index}"
            await subscribe(self.namespace, indexed_name, relay_service, topic)

        message = "aGVsbG8="  # Test message
        for index in range(self.config.num_nodes):
            indexed_name = f"{relay_name}-{index}"
            await send(self.namespace, indexed_name, relay_service, topic, message)

        await asyncio.sleep(20)
        self.log_event("publisher_wait_finished")
        self.log_event("internal_run_finished")
