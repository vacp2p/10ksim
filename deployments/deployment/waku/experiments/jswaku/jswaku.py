import asyncio
from copy import deepcopy
import logging
import os
import random
from asyncio import sleep
from argparse import Namespace
from contextlib import ExitStack
from datetime import timedelta
from pathlib import Path
from typing import Any, List, Literal, Optional

from kubernetes.client import ApiClient
from pydantic import BaseModel, ConfigDict, Field
from ruamel import yaml

from deployment.base_experiment import (
    BaseExperiment,
    find_events,
    format_metadata_timestamps,
    get_valid_shifted_times,
    parse_events_log,
)
from deployment.builders import build_deployment
from kube_utils import (
    dict_get,
    dict_set,
    get_YAML,
    get_flag_value,
    wait_for_rollout,
)
from registry import experiment

logger = logging.getLogger(__name__)


from kubernetes import client, config
from kubernetes.stream import stream


def add_network_delay_to_pod(namespace, pod_name, delay_ms):
    api = client.CoreV1Api()

    command = ["/bin/sh", "-c", f"tc qdisc add dev eth0 root netem delay {delay_ms}ms"]

    try:
        logger.info(f"Attempt to disconnect pod {pod_name}")
        # Execute command inside the pod
        resp = stream(
            api.connect_get_namespaced_pod_exec,
            pod_name,
            namespace,
            command=command,
            stderr=True,
            stdin=False,
            stdout=True,
            tty=False,
        )
        logger.info(f"Command executed in pod {pod_name}. Response: `{resp}`")
    except client.exceptions.ApiException as e:
        logger.error(f"Exception when executing command: {e}")


def remove_network_delay_from_pod(namespace, pod_name):
    api = client.CoreV1Api()

    command = ["/bin/sh", "-c", "tc qdisc del dev eth0 root"]

    try:
        logger.info(f"Attempt to remove network delay from pod: `{pod_name}`")
        resp = stream(
            api.connect_get_namespaced_pod_exec,
            pod_name,
            namespace,
            command=command,
            stderr=True,
            stdin=False,
            stdout=True,
            tty=False,
        )
        logger.info(f"Removed network delay from pod: `{pod_name}` response: `{resp}`")
    except client.exceptions.ApiException as e:
        logger.error(f"Exception when removing delay: {e}")


class JsWakuSettings:

    @staticmethod
    def server_args(sharding: Literal["auto", "static"]):
        if sharding == "auto":
            return {
                "Discv5BootstrapNode": ["$ENR1", "$ENR2", "$ENR3"],
                "Lightpush": "true",
                "Relay": "true",
                "MaxConnections": "500",
                "Rest": "true",
                "RestAdmin": "true",
                "RestAddress": "0.0.0.0",
                "Discv5Discovery": "true",
                "Discv5EnrAutoUpdate": "True",
                "LogLevel": "INFO",
                "MetricsServer": "True",
                "MetricsServerAddress": "0.0.0.0",
                "ClusterId": "2",
                "WebsocketSupport": "true",
                "NumShardsInNetwork": 8,
                "Nat": "extip:${IP}",
            }
        elif sharding == "static":
            return {
                "Discv5BootstrapNode": ["$ENR1", "$ENR2", "$ENR3"],
                "Lightpush": "true",
                "Relay": "true",
                "MaxConnections": "500",
                "Rest": "true",
                "RestAdmin": "true",
                "RestAddress": "0.0.0.0",
                "Discv5Discovery": "true",
                "Discv5EnrAutoUpdate": "True",
                "LogLevel": "INFO",
                "MetricsServer": "True",
                "MetricsServerAddress": "0.0.0.0",
                "ClusterId": "2",
                "WebsocketSupport": "true",
                "NumShardsInNetwork": 1,
                "Shard": "0",
                "Nat": "extip:${IP}",
            }

    @staticmethod
    def server_args_1():
        return {
            "Lightpush": True,
            "Relay": True,
            "MaxConnections": 500,
            "Rest": True,
            "RestAdmin": True,
            "RestAddress": "0.0.0.0",
            "Discv5Discovery": True,
            "Discv5EnrAutoUpdate": True,
            "LogLevel": "INFO",
            "MetricsServer": True,
            "Discv5BootstrapNode": ["$ENR1", "$ENR2", "$ENR3"],
            "MetricsServerAddress": "0.0.0.0",
            "Nat": "extip:${IP}",
            "ClusterId": 2,
            "WebsocketSupport": True,
            "NumShardsInNetwork": 1,
            "Shard": "0",
        }

    @staticmethod
    def set_client_values(values: dict, sharding: Literal["auto", "static"]):
        settings = {
            "waku.nodes.volumes": [{"name": "address-data", "emptyDir": {}}],
            "waku.nodes.volumesMounts": [{"name": "address-data", "mountPath": "/etc/addrs"}],
            "waku.nodes.initContainers": [JsWakuSettings.client_init_container()],
            "waku.nodes.readinessProbe.type": "jswaku",
            "waku.nodes.command.full.container": JsWakuSettings.client_command(sharding),
        }
        for key, value in settings.items():
            dict_set(values, key, value, sep=".", replace_leaf=True)

    @staticmethod
    def client_readiness_probe_command():
        script = """node=127.0.0.1
jswaku_external_port=8080
if curl -s -X GET http://$node:${jswaku_external_port}/waku/v1/peer-info \
    -H "Content-Type: application/json" | jq -e '.peerId' > /dev/null
        """
        return ["/bin/sh", "-c", script]

    @staticmethod
    def client_readiness_probe():
        return {
            "readinessProbe": {
                "exec": {"command": JsWakuSettings.client_readiness_probe_command()},
                "successThreshold": 5,
                "initialDelaySeconds": 5,
                "periodSeconds": 1,
                "failureThreshold": 2,
                "timeoutSeconds": 5,
            }
        }

    @staticmethod
    def client_init_container():
        return {
            "name": "grabaddress",
            "image": "pearsonwhite/get_address_2:4635b8b4eafd0f399579a1a0369f7a4961d4cac2",
            "imagePullPolicy": "IfNotPresent",
            "volumeMounts": [
                {
                    "name": "address-data",
                    "mountPath": "/etc/addrs",
                }
            ],
            "command": [
                "python3",
                "/app/get_address.py",
            ],
            "args": [
                "--num=1",
                '--service-name="zerotesting-lightpush-server.zerotesting-pwhite"',
                '--output-file="/etc/addrs/addrs.env"',
                '--var-name="addrs"',
                "--websocket",
            ],
        }

    @staticmethod
    def client_command(sharding: Literal["auto", "static"]):
        prefix = ["sh", "-c"]
        script = [". /etc/addrs/addrs.env", "echo addrs are $addrs1"]
        if sharding == "auto":
            script += ["/usr/local/bin/docker-entrypoint.sh --cluster-id=2"]
        elif sharding == "static":
            script += ["/usr/local/bin/docker-entrypoint.sh --cluster-id=2 --shard=0"]
        else:
            raise ValueError(f"Sharding param must be 'auto' or 'static'. Given `{sharding}`")
        return prefix + ["\n".join(script) + "\n"]


# TODO naming
# @experiment(name="jswaku-disconnect")
@experiment(name="js-waku")
class JsWakuNodes(BaseExperiment, BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    @classmethod
    def add_parser(cls, subparsers) -> None:
        subparser = subparsers.add_parser(cls.name, help="TODO")
        BaseExperiment.add_args(subparser)

    def _preprocess_event(self, event: Any) -> Any:
        if isinstance(event, str):
            event = {"event": event}
        return super()._preprocess_event(event)

    @classmethod
    def get_metadata_event(cls, events_log_path: str) -> dict:
        events_list = [
            ({"event": "wait_for_clear_finished"}, ("complete.start", timedelta(seconds=0))),
            ({"event": "internal_run_finished"}, ("complete.end", timedelta(seconds=30))),
            ({"event": "publisher_deploy_start"}, ("stable.start", timedelta(minutes=3))),
            (
                {"event": "deployment", "service": "waku/publisher", "phase": "start"},
                ("stable.start", timedelta(minutes=3)),
            ),
            ({"event": "publisher_wait_finished"}, ("stable.end", timedelta(seconds=-30))),
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

        base_metadata = super(JsWakuNodes, cls).get_metadata_event(events_log_path)
        base_metadata.update(metadata)
        return base_metadata

    def _metadata_event(self):
        self.log_event(self.__class__.get_metadata_event(self.events_log_path))

    def log_event(self, event):
        logger.info(event)
        return super().log_event(event)

    def log_event(self, event):
        logger.info(event)
        return super().log_event(event)

    async def random_disconnects(self, deployment: dict, rate: timedelta, duration: timedelta):
        """
        :param rate: Time between each disconnect. Accounts for the time a node is disconnected.
        :param duration: The duration for which a node is disconnected.
        """
        num_nodes = deployment["spec"]["replicas"]
        name = deployment["metadata"]["name"]
        namespace = deployment["metadata"]["namespace"]

        logger.info(f"Starting random disconnects on `{name}`")
        while True:
            logger.info("disconnect loop") # TODO rm
            index = random.randint(0, num_nodes - 1)
            random_name = f"{name}-{index}"
            add_network_delay_to_pod(namespace, random_name, 5000)
            await sleep(duration.total_seconds())
            remove_network_delay_from_pod(namespace, random_name)
            await sleep((rate - duration).total_seconds())

    async def _run(
        self,
        api_client: ApiClient,
        workdir: str,
        args: Namespace,
        values_yaml: Optional[yaml.YAMLObject],
        stack: ExitStack,
    ):
        self.log_event("run_start")
        sharding = values_yaml.get("sharding_type", "static")
        if sharding != "static":
            raise NotImplementedError(
                "Auto sharding not implemented. It should work on the jswaku side, "
                "but the Lightpush server nodes do not establish connectivity."
            )

        await self.deploy(
            api_client,
            stack,
            args,
            values_yaml,
            workdir=workdir,
            service="waku/bootstrap",
            wait_for_ready=True,
            extra_values_paths=[Path(__file__).parent / "bootstrap.values.yaml"],
        )

        lps_values = deepcopy(values_yaml)
        dict_set(
            lps_values, "waku.nodes.command.args", JsWakuSettings.server_args(sharding), sep="."
        )
        lps_deploy = self.build(
            lps_values,
            Path(workdir) / "server",
            "waku/nodes",
            extra_values_paths=[Path(__file__).parent / "lps.values.yaml"],
        )
        await self.deploy(api_client, stack, args, lps_values, deployment_yaml=lps_deploy)


        # nwaku
        # lpc_values = deepcopy(values_yaml)
        # with open(Path(__file__).parent / "./nwaku_lpc.yaml", 'r') as lpc_yaml:
        #     import yaml
        #     lpc_dep = yaml.safe_load(lpc_yaml.read())
        # lpc_deploy = self.deploy(api_client, stack, args, lpc_values, deployment_yaml=lpc_dep)

        # jswaku
        lpc_values = deepcopy(values_yaml)
        JsWakuSettings.set_client_values(lpc_values, sharding)

        lpc_deploy = self.build(
            lpc_values,
            Path(workdir) / "client",
            "waku/nodes",
            extra_values_paths=[Path(__file__).parent / "lpc.values.yaml"],
        )
        await self.deploy(api_client, stack, args, lpc_values, deployment_yaml=lpc_deploy)

        num_nodes = lpc_deploy["spec"]["replicas"]

        publisher = await self.deploy(
            api_client,
            stack,
            args,
            values_yaml,
            service="waku/publisher",
            workdir=workdir,
            extra_values_paths=[Path(__file__).parent / "publisher.values.yaml"],
            wait_for_ready=True,
        )

        dc_task = asyncio.create_task(
            # self.random_disconnects(deployment=lpc_deploy, rate=timedelta(seconds=6), duration=timedelta(seconds=2))
            self.random_disconnects(deployment=lpc_deploy, rate=timedelta(seconds=6), duration=timedelta(seconds=1))
        )

        messages = get_flag_value("messages", publisher["spec"]["containers"][0]["command"])
        delay_seconds = get_flag_value(
            "delay-seconds", publisher["spec"]["containers"][0]["command"]
        )
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
                # TODO [extend condition checks] lambda cond : cond.type == "Ready" and cond.status == "True"
            )

        self.log_event("publisher_messages_finished")
        dc_task.cancel()

        await sleep(20)
        self.log_event("publisher_wait_finished")

        self.log_event("internal_run_finished")
        self._metadata_event()
