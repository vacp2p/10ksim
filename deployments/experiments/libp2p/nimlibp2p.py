import asyncio
import logging
import os
import random
import traceback
from argparse import Namespace
from contextlib import ExitStack
from dataclasses import Field
from datetime import timedelta
from pathlib import Path
from typing import Optional

from core.kube_utils import get_YAML, k8s_obj_to_dict
from experiments.base_experiment import BaseExperiment
from kubernetes.client import ApiClient, V1StatefulSet
from libp2p.bridge import Bridge
from libp2p.builders.builders import Libp2pStatefulSetBuilder
from libp2p.builders.builders import Option as NimLibp2p
from pod_api_requester.builder import PodApiRequesterBuilder
from pod_api_requester.configs import Target
from pod_api_requester.pod_api_requester import PodApiApplicationError, PodApiError, request
from pydantic import BaseModel, ConfigDict, NonNegativeFloat, NonNegativeInt
from registry import experiment

logger = logging.getLogger(__name__)


class EventMapping(BaseModel):
    key: dict
    target: Path
    time_shift: timedelta = Field(default_factory=lambda: timedelta(0))


def waku_links_maps():
    links_map = {
        "grafana": "https://grafana.vaclab.org/d/jIrqsZTIz/nwaku?orgId=1&from={start}&to={end}&timezone=utc",
        "victoria": "https://vlselect.vaclab.org/select/vmui/?#/?query=*&g0.start_input={start}&g0.end_input={end}&g0.relative_time=none",
    }


def add_links(metadata, links_map):
    # For interval_type in [completed, stable] (if they were added).
    for interval_type in metadata.keys():
        try:
            for link_type, base in links_map.items():
                metadata[interval_type][link_type] = base.format(
                    start=metadata[interval_type]["start"], end=metadata[interval_type]["end"]
                )
        except KeyError:
            pass


class BridgeBase:
    def _get_metadata_from_events_list(self, events_log_path: str, events_list: List[EventMapping]):
        # Strip the timedelta for the conversion, to get a list of Tuple[match_dict : dict, path : str].
        events_maps = [(obj.key, obj.target) for obj in events_list]
        metadata = parse_events_log(events_log_path, events_maps)

        # Get timedeltas for each path. dict of {path : timedelta}.
        deltatime_map = {obj.target: obj.time_shift for obj in events_list}
        shifted = get_valid_shifted_times(deltatime_map, metadata)
        metadata.update(shifted)

        metadata = format_metadata_timestamps(metadata)

        return metadata


class Metadata(BridgeBase):
    def _get_metadata_event(self, events_log_path: str):
        events_list = map(
            lambda obj: EventMapping(key=obj[0], target=obj[1], time_shift=obj[2]),
            [
                ({"event": "wait_for_clear_finished"}, "complete.start", timedelta(seconds=0)),
                ({"event": "internal_run_finished"}, "complete.end", timedelta(seconds=30)),
                ({"event": "start_messages"}, "stable.start", timedelta(minutes=3)),
                ({"event": "publisher_messages_finished"}, "stable.end", timedelta(seconds=-30)),
            ],
        )
        metadata = self._get_metadata_from_events_list(events_log_path, events_list)
        return metadata


def build_nodes(
    namespace: str,
    num_nodes: int,
) -> V1StatefulSet:
    return (
        Libp2pStatefulSetBuilder()
        .with_libp2p_config(name="pod", namespace=namespace, num_nodes=num_nodes)
        .with_option(NimLibp2p.peers, 100)
        .with_option(NimLibp2p.muxer, "yamux")
        .with_option(NimLibp2p.connect_to, 10)
        .build()
    )


@experiment(name="nimlibp2p")
class NimLibp2pExperiment(BaseExperiment, BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    @classmethod
    def add_parser(cls, subparsers) -> None:
        subparser = subparsers.add_parser(cls.name, help="nimlibp2p2 experiment")
        BaseExperiment.add_args(subparser)

    def _get_metadata(self) -> dict:
        return Bridge().get_metadata(self.events_log_path)

    class ExpConfig(BaseModel):
        model_config = ConfigDict(extra="ignore")

        num_nodes: NonNegativeInt = 10
        num_messages: NonNegativeInt = 20
        delay_cold_start: NonNegativeFloat = 60
        delay_after_publish: NonNegativeFloat = 1

    async def _run(
        self,
        api_client: ApiClient,
        workdir: str,
        args: Namespace,
        values_yaml: Optional[dict],
        stack: ExitStack,
    ):
        self.log_event("run_start")

        config = self.ExpConfig(**values_yaml)
        self.log_metadata({"params": vars(config)})

        # Publisher
        publisher = (
            PodApiRequesterBuilder().with_namespace(args.namespace).with_mode("server").build()
        )
        await self.deploy(
            api_client, stack, args, values_yaml, deployment=publisher, wait_for_ready=True
        )

        # Nodes
        nodes = build_nodes(
            namespace=args.namespace,
            num_nodes=config.num_nodes,
        )
        name = nodes.metadata.name
        namespace = nodes.metadata.namespace

        out_path = Path(workdir) / name / f"{name}.yaml"
        os.makedirs(out_path.parent, exist_ok=True)
        logger.info(f"dumping deployment `{name}` to `{out_path}`")
        with open(out_path, "w") as out_file:
            yaml = get_YAML()
            yaml.dump(k8s_obj_to_dict(nodes), out_file)
        await self.deploy(api_client, stack, args, values_yaml, deployment=nodes)

        await asyncio.sleep(config.delay_cold_start)

        logger.info(f"Starting publish loop for nodes in `{name}`")

        self.log_event("start_messages")

        for _ in range(config.num_messages):
            index = random.randint(0, config.num_nodes - 1)
            random_name = f"{name}-{index}"
            self.log_event({"event": "publish", "node": random_name})
            try:
                target = Target(
                    name="libp2p-node",
                    name_template=random_name,
                    service="nimp2p-service",
                    port=8645,
                )
                await request(
                    namespace=namespace, target=target, endpoint="libp2p-dst-node-publish"
                )
            except PodApiApplicationError as e:
                logger.error(f"PodApiApplicationError: {e} {traceback.format_exc()}")
            except PodApiError as e:
                logger.error(f"PodApiError: {e} {traceback.format_exc()}")
            except Exception as e:
                logger.error(f"Other exception: {e} {traceback.format_exc()}")

            await asyncio.sleep(config.delay_after_publish)

        self.log_event("publisher_messages_finished")

        await asyncio.sleep(20)
        self.log_event("publisher_wait_finished")

        self.log_event("internal_run_finished")
