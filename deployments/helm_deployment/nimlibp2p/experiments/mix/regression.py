import logging
import os
import re
import urllib
from argparse import ArgumentParser, Namespace
from asyncio import sleep
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from pathlib import Path
from typing import Optional, Tuple

from core.base_bridge import format_metadata_timestamps, get_valid_shifted_times, parse_events_log
from core.kube_utils import (
    dict_get,
    dict_set,
    get_cleanup,
    get_future_time,
    kubectl_apply,
    wait_for_time,
)
from experiments.base_experiment import BaseExperiment
from helm_deployment.builders import build_deployment
from kubernetes.client import ApiClient
from pydantic import BaseModel, ConfigDict, Field, PositiveInt
from registry import experiment
from ruamel import yaml

logger = logging.getLogger(__name__)


def set_delay(
    values_yaml: yaml.YAMLObject, hours_key: str, minutes_key: str, delay: str
) -> yaml.YAMLObject:
    result = deepcopy(values_yaml)
    future_time = get_future_time(timedelta(seconds=int(delay)))
    dict_set(result, minutes_key, future_time.minute, sep=".", replace_leaf=True)
    dict_set(result, hours_key, future_time.hour, sep=".", replace_leaf=True)
    return result


@experiment(name="nimlibp2p-mix-nodes")
class NimMixNodes(BaseExperiment, BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    release_name: str = Field(default="nim-regression-nodes")
    this_dir: str = Field(default=Path(os.path.dirname(__file__)))
    hours_key: str = Field(default="nimlibp2p.nodes.hours", no_init=True)
    minutes_key: str = Field(default="nimlibp2p.nodes.minutes", no_init=True)

    @staticmethod
    def add_args(subparser: ArgumentParser):
        subparser.add_argument(
            "--delay",
            type=str,
            dest="delay",
            required=False,
            help="For nimlibp2p tests only. The delay before nodes activate in string format (eg. 1hr20min)",
        )

    @classmethod
    def add_parser(cls, subparsers) -> None:
        subparser = subparsers.add_parser(cls.name, help="Run a regression_nodes test using waku.")
        BaseExperiment.add_args(subparser)
        NimMixNodes.add_args(subparser)

    @classmethod
    def get_metadata_event(_cls, events_log_path: str):
        events_list = [
            ({"event": "wait_for_clear_finished"}, ("times.start", timedelta(seconds=0))),
            ({"event": "begin_messages"}, ("messages.start", timedelta(seconds=0))),
            ({"event": "end_messages"}, ("messages.end", timedelta(seconds=0))),
            ({"event": "cleanup_start"}, ("times.end", timedelta(seconds=0))),
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

        def end_time_format(time_str: str) -> str:
            return time_str.split(".")[0]

        def range_input(start, end):
            fmt = "%Y-%m-%dT%H:%M:%S.%fZ"
            t1 = datetime.strptime(start, fmt)
            t2 = datetime.strptime(end, fmt)
            delta = t2 - t1
            total_seconds = int(delta.total_seconds())
            minutes, seconds = divmod(total_seconds, 60)
            result = f"&g0.range_input={minutes}m{seconds}s"
            return result

        # For interval_type in [completed, stable] (if they were added).
        for interval_type in metadata.keys():
            try:
                for link_type, base in links_map.items():
                    value = base.format(
                        start=urllib.parse.quote(metadata[interval_type]["start"]),
                        end=urllib.parse.quote(end_time_format(metadata[interval_type]["end"])),
                    )
                    if link_type == "victoria":
                        value = value + range_input(
                            metadata[interval_type]["start"], metadata[interval_type]["end"]
                        )
                    metadata[interval_type][link_type] = value
            except KeyError:
                pass

        # Get experiment parameter data
        params_event = [
            ({"event": "deployment", "type": "nimlibp2p", "phase": "start"}, "experiment.params")
        ]
        extract = lambda item: item
        param_metadata = parse_events_log(events_log_path, params_event, extract=extract)
        metadata.update(param_metadata)

        return metadata

    def _metadata_event(self):
        self.log_event(self.__class__.get_metadata_event(self.events_log_path))

    def log_event(self, event):
        logger.info(event)
        return super().log_event(event)

    def _build_all(
        self, workdir: str, cli_values: yaml.YAMLObject, delay: Optional[str]
    ) -> Tuple[yaml.YAMLObject, PositiveInt]:

        num_gossip = dict_get(cli_values, "nimlibp2p.nodes.numGossip", sep=".")
        num_mix_nodes = dict_get(cli_values, "nimlibp2p.nodes.numMix", sep=".")
        total_nodes = num_gossip + num_mix_nodes

        builds = []

        mix_nodes_values = deepcopy(cli_values)
        gossip_nodes_values = deepcopy(cli_values)
        # isPublisher is determined in main.nim logic.
        dict_set(
            mix_nodes_values, "nimlibp2p.nodes.env.vars.isMix", True, sep=".", replace_leaf=True
        )
        dict_set(
            mix_nodes_values,
            "nimlibp2p.nodes.env.vars.SELFTRIGGER",
            True,
            sep=".",
            replace_leaf=True,
        )
        dict_set(
            mix_nodes_values,
            "nimlibp2p.nodes.env.vars.nodes",
            total_nodes,
            sep=".",
            replace_leaf=True,
        )
        dict_set(
            mix_nodes_values,
            "nimlibp2p.nodes.env.vars.numMix",
            num_mix_nodes,
            sep=".",
            replace_leaf=True,
        )
        dict_set(mix_nodes_values, "nimlibp2p.nodes.name", f"mix", sep=".", replace_leaf=True)
        dict_set(
            mix_nodes_values, "nimlibp2p.nodes.numNodes", num_mix_nodes, sep=".", replace_leaf=True
        )
        workdir_path = Path(workdir)
        mix_workdir = workdir_path / f"mix"
        os.makedirs(mix_workdir, exist_ok=True)
        dep, delay = self._build_one(mix_workdir.as_posix(), mix_nodes_values, delay)
        builds.append(dep)

        dict_set(
            gossip_nodes_values, "nimlibp2p.nodes.env.vars.isMix", False, sep=".", replace_leaf=True
        )
        dict_set(
            gossip_nodes_values,
            "nimlibp2p.nodes.env.vars.SELFTRIGGER",
            False,
            sep=".",
            replace_leaf=True,
        )
        dict_set(
            gossip_nodes_values,
            "nimlibp2p.nodes.env.vars.nodes",
            total_nodes,
            sep=".",
            replace_leaf=True,
        )
        dict_set(
            gossip_nodes_values,
            "nimlibp2p.nodes.env.vars.numMix",
            num_mix_nodes,
            sep=".",
            replace_leaf=True,
        )
        dict_set(gossip_nodes_values, "nimlibp2p.nodes.name", f"pod", sep=".", replace_leaf=True)
        dict_set(
            gossip_nodes_values, "nimlibp2p.nodes.numNodes", num_gossip, sep=".", replace_leaf=True
        )
        workdir_path = Path(workdir)
        pod_workdir = workdir_path / f"pod"
        os.makedirs(pod_workdir, exist_ok=True)
        dep, delay = self._build_one(pod_workdir.as_posix(), gossip_nodes_values, delay)
        builds.append(dep)

        return builds, delay

    def _build_one(
        self, workdir: str, cli_values: yaml.YAMLObject, delay: Optional[str]
    ) -> Tuple[yaml.YAMLObject, PositiveInt]:
        build = lambda values: build_deployment(
            deployment_dir=os.path.join(self.this_dir, "..", "..", "nodes"),
            workdir=os.path.join(workdir, "nodes"),
            cli_values=values,
            name=self.release_name,
            extra_values_names=[],
            extra_values_paths=[os.path.join(self.this_dir, f"nodes.values.yaml")],
        )
        if delay is None:
            _deployment = build(cli_values)
            num_nodes = dict_get(cli_values, "nimlibp2p.nodes.numNodes", sep=".")
            # Assume it takes ~3 seconds to bring up each node.
            delay = (3 * 60) + (num_nodes * 3)
            logger.info(f"Using default delay (in seconds): {delay}")

        cli_values = set_delay(cli_values, self.hours_key, self.minutes_key, delay)
        return build(cli_values), delay

    async def _run(
        self,
        api_client: ApiClient,
        workdir: str,
        args: Namespace,
        values_yaml: Optional[yaml.YAMLObject],
        stack: ExitStack,
    ):
        logger.info("Building kubernetes configs.")

        all_nodes_deploy, delay = self._build_all(workdir, values_yaml, delay=args.delay)
        mix_nodes_deploy = all_nodes_deploy[0]
        _gossip_nodes_deploy = all_nodes_deploy[1]
        logger.info(f"Using delay: {delay}")

        this_time = datetime.now(dt_timezone.utc)
        logger.info(f"Current UTC time: {this_time.hour:02d}:{this_time.minute:02d}")

        future_time = get_future_time(timedelta(seconds=int(delay)))
        logger.info(f"Messages will begin at: {future_time.hour:02d}:{future_time.minute:02d}")

        namespace = mix_nodes_deploy["metadata"]["namespace"]
        logger.info(f"Applying deployment to namespace: `{namespace}`")

        self._wait_until_clear(
            api_client=api_client,
            namespace=namespace,
            skip_check=args.skip_check,
        )

        cleanup = get_cleanup(
            api_client=api_client,
            namespace=namespace,
            deployments=all_nodes_deploy,
        )
        stack.callback(cleanup)

        async def wipe_data():
            logger.info("wiping shared volume data...")
            wiper_path = self.this_dir / "wiper.yaml"
            with open(wiper_path, "r") as f:
                from ruamel import yaml

                wiper_deployment = yaml.safe_load(f.read())
            logger.info(f"wiper_deployment: {wiper_deployment}")
            wiper_cleanup = get_cleanup(
                api_client=api_client,
                namespace=namespace,
                deployments=[wiper_deployment],
            )
            await sleep(2)
            kubectl_apply(wiper_deployment)
            await sleep(14)
            wiper_cleanup()

        stack.callback(wipe_data)

        # "tc qdisc add dev eth0 root netem delay {{ .Values.nimlibp2p.nodes.network.delay }}ms {{ .Values.nimlibp2p.nodes.network.jitter }}ms distribution normal"
        def extract_delay_and_jitter(command_str: str):
            try:
                match = re.search(
                    r"delay (?P<delay>\d+)ms(?: (?P<jitter>\d+)ms)?(?: distribution normal)?",
                    command_str,
                )
                return match.groupdict()
            except AttributeError:
                return {"delay": None, "jitter": None}

        try:
            network_params = extract_delay_and_jitter(
                mix_nodes_deploy["spec"]["template"]["spec"]["initContainers"][0]["command"][2]
            )
        except KeyError:
            network_params = {"delay": 0, "jitter": 0}

        container_image = mix_nodes_deploy["spec"]["template"]["spec"]["containers"][0]["image"]
        image, tag = container_image.split(":")

        msgs = dict_get(values_yaml, "nimlibp2p.nodes.env.vars.messages", sep=".")
        rate = dict_get(values_yaml, "nimlibp2p.nodes.env.vars.msgRate", sep=".")

        num_gossip_nodes = dict_get(values_yaml, "nimlibp2p.nodes.numGossip", sep=".")
        mix_nodes = dict_get(values_yaml, "nimlibp2p.nodes.numMix", sep=".")

        self.log_event(
            {
                "event": "deployment",
                "type": "nimlibp2p",
                "name": mix_nodes_deploy["metadata"]["name"],
                "mix_nodes": mix_nodes,
                "num_gossip_nodes": num_gossip_nodes,
                "image": {
                    "repo": image,
                    "tag": tag,
                },
                "delay": network_params.get("delay") or 0,
                "jitter": network_params.get("jitter") or 0,
                "phase": "start",
                "messages": msgs,
                "message_rate": rate,
            }
        )

        for nodes_pod in all_nodes_deploy:
            logger.info("deploying...")
            kubectl_apply(nodes_pod, namespace=namespace)

        logger.info("Deployment applied.")

        now = datetime.now(dt_timezone.utc)
        logger.info(f"this_time: {datetime.now(dt_timezone.utc)}")
        difference = future_time - now
        logger.info(
            f"Waiting for cron job begin time: {future_time.hour:02d}:{future_time.minute:02d} ({difference} from now)"
        )
        wait_for_time(future_time)  # Wait until the nodes begin.
        self.log_event("begin_messages")

        delay_arg = int(network_params.get("delay") or 0)
        jitter_arg = int(network_params.get("jitter") or 0)

        await sleep(10)  # Wait for nodes to get connected.

        time_to_resolve = (msgs + 1) * (rate + (delay_arg + jitter_arg + 50)) + 30000
        time_to_resolve = timedelta(milliseconds=time_to_resolve)
        logger.info(f"Waiting for messages to resolve. Sleep: {time_to_resolve}")
        start_time = datetime.now()
        time_elapsed = datetime.now() - start_time
        while time_elapsed < time_to_resolve:
            await sleep(20)
            logger.info(f"waiting: {(time_elapsed.seconds/time_to_resolve.seconds)*100}%")
            time_elapsed = datetime.now() - start_time
        self.log_event("end_messages")

        self._metadata_event()

        this_time = datetime.now(dt_timezone.utc)
        logger.info(
            f"Test completed successfully at UTC time: {this_time.hour:02d}:{this_time.minute:02d}"
        )
