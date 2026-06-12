#!/usr/bin/env python3

import asyncio
import logging
import traceback

from pydantic import BaseModel, ConfigDict, NonNegativeFloat, NonNegativeInt

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
    delay_cold_start: NonNegativeFloat = 60
    delay_after_publish: NonNegativeFloat = 1


_LOGOSCORE_PUBLISHER = {
    "service_name": "core-external",
    "app": "zerotenkay-core2",
}


async def init_node(namespace, name_with_index):
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

    try:
        target = Target(
            name="pub",
            name_template=name_with_index,
            service="core-nodes-internal",
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


async def init_token(namespace, name_with_index):
    try:
        target = Target(
            name="pub",
            name_template=name_with_index,
            service="core-nodes-internal",
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


@experiment(name="core")
class NimLibp2pExperiment(BaseExperiment[ExpConfig]):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    @classmethod
    def add_parser(cls, subparsers) -> None:
        subparser = subparsers.add_parser(cls.name, help="nimlibp2p2 experiment")
        BaseExperiment.add_args(subparser)

    def _get_metadata(self) -> dict:
        return Bridge().get_metadata(self.events_log_path)

    async def _run(self):
        self.log_event("run_start")

        publisher_builder = (
            LogoscorePodApiRequester()
            .with_namespace(self.namespace)
            .with_mode("server")
            .with_logoscore_profile(self.namespace)
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

        nodes_builder = (
            NodesBuilder()
            .with_config(namespace=self.namespace)
            .with_replicas(self.config.num_nodes)
        )
        nodes = nodes_builder.build()
        await self.deploy(deployment=nodes, wait_for_ready=True)
        nodes_deps = nodes_builder.build_dependencies()
        for _kind, deps in nodes_deps.items():
            for dep in deps:
                await self.deploy(deployment=dep, wait_for_ready=True)

        logger.info(f"Waiting for cold_start_delay: {self.config.delay_cold_start}")
        await asyncio.sleep(self.config.delay_cold_start)

        name = nodes.metadata.name
        self.log_event("init_logoscore_nodes")
        for index in range(self.config.num_nodes):
            indexed_name = f"{name}-{index}"
            try:
                await init_token(self.namespace, indexed_name)
            except Exception as e:
                logger.error(f"e: {e}")
            await init_node(self.namespace, indexed_name)

        # logger.info(f"Starting publish loop for nodes in `{name}`")
        # self.log_event("start_messages")
        # for msg_index in range(config.num_messages):
        #     index = random.randint(0, config.num_nodes - 1)
        #     random_name = f"{name}-{index}"
        #     self.log_event({"event": "publish", "node": random_name, "index": msg_index})
        #     await asyncio.sleep(self.config.delay_after_publish)
        # self.log_event("publisher_messages_finished")

        await asyncio.sleep(20)
        self.log_event("publisher_wait_finished")
        self.log_event("internal_run_finished")
