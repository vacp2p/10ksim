import logging
import os
import time
from argparse import Namespace
from contextlib import ExitStack
from datetime import timedelta
from pathlib import Path
from typing import Any, List, Optional

from core.base_bridge import format_metadata_timestamps, get_valid_shifted_times, parse_events_log
from core.kube_utils import get_flag_value, wait_for_rollout
from experiments.base_experiment import BaseExperiment
from kubernetes.client import ApiClient
from pydantic import BaseModel, ConfigDict, Field
from registry import experiment
from ruamel import yaml

logger = logging.getLogger(__name__)


@experiment(name="waku-regression-nodes")
class WakuRegressionNodes(BaseExperiment, BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    release_name: str = Field(default="waku-regression-nodes")

    deployment_dir: str = Field(default=Path(os.path.dirname(__file__)).parent.parent)
    extra_paths: List[Path] = [
        Path(os.path.dirname(__file__)) / f"bootstrap.values.yaml",
        Path(os.path.dirname(__file__)) / f"nodes.values.yaml",
        Path(os.path.dirname(__file__)) / f"publisher.values.yaml",
    ]

    @classmethod
    def add_parser(cls, subparsers) -> None:
        subparser = subparsers.add_parser(cls.name, help="Run a regression_nodes test using waku.")
        BaseExperiment.add_args(subparser)

    def _preprocess_event(self, event: Any) -> Any:
        if isinstance(event, str):
            event = {"event": event}
        return super()._preprocess_event(event)

    @classmethod
    def _get_metadata_event(_cls, events_log_path: str):
        events_list = [
            ({"event": "wait_for_clear_finished"}, ("complete.start", timedelta(seconds=0))),
            ({"event": "internal_run_finished"}, ("complete.end", timedelta(seconds=30))),
            ({"event": "publisher_deploy_start"}, ("stable.start", timedelta(minutes=3))),
            (
                {"event": "deployment", "service": "waku/publisher", "phase": "start"},
                ("stable.start", timedelta(minutes=3)),
            ),
            ({"event": "publisher_messages_finished"}, ("stable.end", timedelta(seconds=-30))),
        ]

        # Strip the timedelta for the conversion, to get a list of Tuple[match_dict : dict, path : str].
        events_maps = [(obj[0], obj[1][0]) for obj in events_list]
        metadata = parse_events_log(events_log_path, events_maps)

        # Get timedeltas for each path. dict of {path : timedelta}.
        deltatime_map = {obj[1][0]: obj[1][1] for obj in events_list}
        shifted = get_valid_shifted_times(deltatime_map, metadata)
        metadata.update(shifted)

        metadata = format_metadata_timestamps(metadata)

        # Add links.
        links_map = {
            "grafana": "https://grafana.vaclab.org/d/jIrqsZTIz/nwaku?orgId=1&from={start}&to={end}&timezone=utc",
            "victoria": "https://vlselect.vaclab.org/select/vmui/?#/?query=*&g0.start_input={start}&g0.end_input={end}&g0.relative_time=none",
        }
        # For interval_type in [completed, stable] (if they were added).
        for interval_type in metadata.keys():
            try:
                for link_type, base in links_map.items():
                    metadata[interval_type][link_type] = base.format(
                        start=metadata[interval_type]["start"], end=metadata[interval_type]["end"]
                    )
            except KeyError:
                pass
        return metadata

    def _metadata_event(self, events_log_path: str):
        self.log_event(self.__class__._get_metadata_event(self.events_log_path))

    def log_event(self, event):
        logger.info(event)
        return super().log_event(event)

    def log_event(self, event):
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
        async def deploy(service, values, *, wait_for_ready=False):
            try:
                values = values._data
            except AttributeError:
                pass
            return await self.deploy(
                api_client,
                stack,
                args,
                values,
                workdir=workdir,
                service=service,
                wait_for_ready=wait_for_ready,
                extra_values_paths=self.extra_paths,
            )

        self.log_event("run_start")

        await deploy("waku/bootstrap", values_yaml, wait_for_ready=True)

        nodes = await deploy("waku/nodes", values_yaml, wait_for_ready=True)
        num_nodes = nodes["spec"]["replicas"]

        publisher = await deploy("waku/publisher", values_yaml, wait_for_ready=True)
        messages = get_flag_value("messages", publisher["spec"]["containers"][0]["command"])
        delay_seconds = get_flag_value(
            "delay-seconds", publisher["spec"]["containers"][0]["command"]
        )

        if not args.dry_run:
            await wait_for_rollout(
                publisher["kind"],
                publisher["metadata"]["name"],
                publisher["metadata"]["namespace"],
                20,
                api_client,
                ("Ready", "True"),
                # TODO [extend condition checks] lambda cond : cond.type == "Ready" and cond.status == "True"
            )
        self.log_event("publisher_deploy_finished")

        timeout = (num_nodes + 5) * messages * delay_seconds * 120
        logger.info(f"Waiting for Ready=False. Timeout: {timeout}")

        if not args.dry_run:
            await wait_for_rollout(
                publisher["kind"],
                publisher["metadata"]["name"],
                publisher["metadata"]["namespace"],
                timeout,
                api_client,
                ("Ready", "False"),
                # TODO: consider state.reason == .completed
            )
        self.log_event("publisher_messages_finished")
        time.sleep(20)
        self.log_event("publisher_wait_finished")

        self.log_event("internal_run_finished")
        self._metadata_event(self.events_log_path)
