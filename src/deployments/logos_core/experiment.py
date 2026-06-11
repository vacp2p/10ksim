#!/usr/bin/env python3

import asyncio
import logging
import traceback
from argparse import Namespace
from contextlib import ExitStack
from typing import Literal, Optional

from kubernetes.client import ApiClient, V1StatefulSet
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

Muxer = Literal["yamux", "quic", "mplex"]


class ExpConfig(BaseModel):
    num_nodes: NonNegativeInt = 30
    num_messages: NonNegativeInt = 20
    message_size_bytes: NonNegativeInt = 1000
    delay_cold_start: NonNegativeFloat = 60
    delay_after_publish: NonNegativeFloat = 1
    muxer: Muxer = "yamux"
    image: Image = Image(repo="pearsonwhite/dst-nimlibp2p-logging", tag="wip-4.2-1.16.0-amd")
    connect_to: NonNegativeInt = 10
    network_delay: NonNegativeInt = 0
    network_jitter: NonNegativeInt = 0
    node_start_delay: NonNegativeInt = 60


def build_logoscore_nodes(namespace: str) -> V1StatefulSet:
    return NodesBuilder().with_config(namespace).build()


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
class NimLibp2pExperiment(BaseExperiment, BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    @classmethod
    def add_parser(cls, subparsers) -> None:
        subparser = subparsers.add_parser(cls.name, help="nimlibp2p2 experiment")
        BaseExperiment.add_args(subparser)

    def _get_metadata(self) -> dict:
        return Bridge().get_metadata(self.events_log_path)

    async def _run(
        self,
        api_client: ApiClient,
        workdir: str,
        args: Namespace,
        values_yaml: Optional[dict],
        stack: ExitStack,
    ):
        self.log_event("run_start")

        config = ExpConfig(**values_yaml)

        self.log_metadata({"params": vars(config)})

        publisher_builder = (
            LogoscorePodApiRequester()
            .with_namespace(args.namespace)
            .with_mode("server")
            .with_logoscore_profile(args.namespace)
        )

        dependencies = publisher_builder.build_dependencies()
        for _name, dep_list in dependencies.items():
            for dep in dep_list:
                logger.info(f"Deploying dependency: {_name}")
                logger.info(f"{dep.metadata.namespace}")
                logger.info(f"{dep.metadata.name}")
                logger.info(f"{type(dep.metadata)}")
                # import pdb; pdb.set_trace()
                await self.deploy(
                    api_client, stack, args, values_yaml, deployment=dep, wait_for_ready=True
                )

        await self.deploy(
            api_client,
            stack,
            args,
            values_yaml,
            deployment=publisher_builder.build(),
            wait_for_ready=True,
        )

        nodes = build_logoscore_nodes(args.namespace)
        await self.deploy(
            api_client,
            stack,
            args,
            values_yaml,
            deployment=nodes,
            wait_for_ready=True,
        )

        logger.info(f"Waiting for cold_start_delay: {config.delay_cold_start}")
        await asyncio.sleep(config.delay_cold_start)

        name = nodes.metadata.name
        self.log_event("init_logoscore_nodes")
        config.num_nodes = 2  # TODO
        for index in range(config.num_nodes):
            indexed_name = f"{name}-{index}"
            try:
                await init_token(args.namespace, indexed_name)
            except Exception as e:
                logger.error(f"e: {e}")
            await init_node(args.namespace, indexed_name)
            await asyncio.sleep(config.delay_after_publish)

        # logger.info(f"Starting publish loop for nodes in `{name}`")
        # self.log_event("start_messages")
        # for msg_index in range(config.num_messages):
        #     index = random.randint(0, config.num_nodes - 1)
        #     random_name = f"{name}-{index}"
        #     self.log_event({"event": "publish", "node": random_name, "index": msg_index})
        # self.log_event("publisher_messages_finished")

        await asyncio.sleep(20)
        self.log_event("publisher_wait_finished")
        self.log_event("internal_run_finished")
