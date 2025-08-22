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
    assert_equals,
    dict_apply,
    dict_get,
    dict_partial_compare,
    dict_set,
    dict_visit,
    get_cleanup,
    get_flag_value,
    kubectl_apply,
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

    @staticmethod
    def add_parser(subparsers) -> None:
        subparser = subparsers.add_parser(
            "waku-regression-nodes", help="Run a regression_nodes test using waku."
        )
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

    def _run(
        self,
        api_client: ApiClient,
        workdir: str,
        args: Namespace,
        values_yaml: Optional[yaml.YAMLObject],
        stack: ExitStack,
    ):
        self.log_event("run_start")

        # TODO [values param checking]: Add friendly error messages for missing/extraneous variables in values.yaml.
        logger.info("Building kubernetes configs.")
        nodes = self._build(workdir, values_yaml, "nodes")
        bootstrap = self._build(workdir, values_yaml, "bootstrap")

        self.log_event({"event": "deployment", "service": "waku/publisher", "phase": "start"})
        publisher = self._build(workdir, values_yaml, "publisher")

        # Sanity check
        namespace = bootstrap["metadata"]["namespace"]
        logger.info(f"namespace={namespace}")
        assert_equals(nodes["metadata"]["namespace"], namespace)
        assert_equals(publisher["metadata"]["namespace"], namespace)

        # TODO [metadata output]: log start time to output file here.
        logger.info("Applying kubernetes configs.")

        cleanup = get_cleanup(
            api_client=api_client,
            namespace=namespace,
            deployments=[bootstrap, nodes, publisher],
        )
        stack.callback(cleanup)

        self._wait_until_clear(
            api_client=api_client,
            namespace=namespace,
            skip_check=args.skip_check,
        )

        self.log_event("deployments_start")

        # Apply bootstrap
        logger.info("Applying bootstrap")
        kubectl_apply(bootstrap, namespace=namespace)
        logger.info("bootstrap applied. Waiting for rollout.")
        wait_for_rollout(bootstrap["kind"], bootstrap["metadata"]["name"], namespace, 2000)

        num_nodes = nodes["spec"]["replicas"]
        messages = get_flag_value("messages", publisher["spec"]["containers"][0]["command"])
        delay_seconds = get_flag_value(
            "delay-seconds", publisher["spec"]["containers"][0]["command"]
        )

        # Apply nodes configuration
        logger.info("Applying nodes")
        kubectl_apply(nodes, namespace=namespace)
        logger.info("nodes applied. Waiting for rollout.")
        timeout = num_nodes * 3000
        wait_for_rollout(nodes["kind"], nodes["metadata"]["name"], namespace, timeout)

        self.log_event("nodes_deploy_finished")
        logger.info("nodes rolled out. wait to stablize")
        time.sleep(60)
        self.log_event("publisher_deploy_start")
        logger.info("delay over")

        # TODO [metadata output]: log publish message start time
        # Apply publisher configuration
        logger.info("applying publisher")
        kubectl_apply(publisher, namespace=namespace)
        logger.info("publisher applied. Waiting for rollout.")
        wait_for_rollout(
            publisher["kind"],
            publisher["metadata"]["name"],
            namespace,
            20,
            api_client,
            ("Ready", "True"),
            # TODO [extend condition checks] lambda cond : cond.type == "Ready" and cond.status == "True"
        )
        self.log_event("publisher_deploy_finished")
        logger.info("publisher rollout done.")

        logger.info("---publisher is up. begin messages")

        timeout = num_nodes * messages * delay_seconds * 120
        logger.info(f"Waiting for Ready=False. Timeout: {timeout}")

        wait_for_rollout(
            publisher["kind"],
            publisher["metadata"]["name"],
            namespace,
            timeout,
            api_client,
            ("Ready", "False"),
        )
        # TODO: consider state.reason == .completed
        logger.info("---publisher messages finished. wait 20 seconds")
        self.log_event("publisher_messages_finished")
        time.sleep(20)
        self.log_event("publisher_wait_finished")
        logger.info("---20seconds is over.")
        # TODO [metadata output]: log publish message end time

        logger.info("Finished waku regression test.")
        self.log_event("internal_run_finished")
        self._metadata_event(self.events_log_path)
