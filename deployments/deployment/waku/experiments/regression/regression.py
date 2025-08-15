import json
import logging
import os
import time
from argparse import Namespace
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from kubernetes.client import ApiClient
from pydantic import BaseModel, ConfigDict, Field
from ruamel import yaml

from deployment.base_experiment import BaseExperiment
from deployment.builders import build_deployment
from kube_utils import (
    dict_apply,
    dict_get,
    dict_partial_compare,
    dict_set,
    dict_visit,
    get_flag_value,
    wait_for_rollout,
)
from registry import experiment

logger = logging.getLogger(__name__)


def parse_events_log(
    log_path: str,
    events_list: List[Tuple[Dict[str, str], str]],
    *,
    extract: Callable[[dict], Any] | None = None,
) -> dict:
    """
    Return a new dict constructed by parsing the event log.
    Each line in `log_path` is converted to an event (dict).
    If the event contains all of the (key, value) items from a dict in `events_list`, then the event is converted to a new value using `extract(event)` and added at `path` in the new dict, where `path` is the value from the `events_list`.

    :param log_path: Path to events log.
    :param events_list: List of tuples mapping a dict to compare to the line to a path in the return dict.
    :param extract: A function mapping the json loaded from the event log to the value in the return dict.
    :return: dict constructed from extracting matchign lines from log_path and converting them to values using `extract`.
    :rtype: dict
    """
    if extract is None:
        extract = lambda event: datetime.strptime(event["timestamp"], "%Y-%m-%d %H:%M:%S")
    return_dict = {}
    with open(log_path, "r") as events_log:
        for line in events_log:
            event = json.loads(line)
            for key, path in events_list:
                try:
                    if dict_partial_compare(event, key):
                        new_value = extract(event)
                        dict_set(
                            return_dict,
                            path,
                            new_value,
                            sep=".",
                        )
                except KeyError:
                    pass
    return return_dict


def format_metadata_timestamps(metadata: dict) -> dict:
    def format_item(node):
        try:
            return node.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        except AttributeError:
            pass

    return dict_apply(metadata, format_item)


def get_valid_shifted_times(deltatime_map: dict[str, timedelta], metadata: dict) -> dict:
    shifted = deepcopy(metadata)
    for path, delta in deltatime_map.items():
        time_value = dict_get(shifted, path, default=None, sep=".")
        if time_value is not None:
            shifted_time = time_value + delta
            dict_set(shifted, path, shifted_time, sep=".", replace_leaf=True)

    filtered = {}

    def filter(path, obj):
        try:
            start_dt = obj["start"]
            end_dt = obj["end"]
            if end_dt <= start_dt:
                return
            dict_set(filtered, path / "start", start_dt)
            dict_set(filtered, path / "end", end_dt)
        except (KeyError, TypeError) as e:
            pass

    dict_visit(shifted, filter)

    return filtered


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

    def _build(
        self,
        workdir: str,
        values_yaml: Optional[yaml.YAMLObject],
        service: str,
    ) -> yaml.YAMLObject:
        this_dir = Path(os.path.dirname(__file__))

        return build_deployment(
            deployment_dir=self.deployment_dir / service,
            workdir=os.path.join(workdir, service),
            cli_values=values_yaml,
            name="waku-regression-nodes",
            extra_values_names=[],
            extra_values_paths=[this_dir / f"{service}.values.yaml"],
        )

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

    def _run(
        self,
        api_client: ApiClient,
        workdir: str,
        args: Namespace,
        values_yaml: Optional[yaml.YAMLObject],
        stack: ExitStack,
    ):
        def deploy(service, values, *, wait_for_ready=False):
            try:
                values = values._data
            except AttributeError:
                pass
            return self.deploy(
                api_client,
                stack,
                args,
                values,
                workdir,
                service,
                wait_for_ready=wait_for_ready,
                extra_values_paths=self.extra_paths,
            )

        self.log_event("run_start")

        deploy("waku/bootstrap", values_yaml, wait_for_ready=True)

        nodes = deploy("waku/nodes", values_yaml, wait_for_ready=True)
        num_nodes = nodes["spec"]["replicas"]

        publisher = deploy("waku/publisher", values_yaml, wait_for_ready=True)
        messages = get_flag_value("messages", publisher["spec"]["containers"][0]["command"])
        delay_seconds = get_flag_value(
            "delay-seconds", publisher["spec"]["containers"][0]["command"]
        )

        if not args.dry_run:
            wait_for_rollout(
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
            wait_for_rollout(
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
