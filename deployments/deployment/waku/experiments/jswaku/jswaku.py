from copy import deepcopy
import logging
import os
import time
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
    format_metadata_timestamps,
    get_valid_shifted_times,
    parse_events_log,
)
from deployment.builders import build_deployment
from kube_utils import (
    dict_get,
    dict_set,
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
        logger.info(f"Command executed in pod {pod_name}: {resp}")
    except client.exceptions.ApiException as e:
        logger.error(f"Exception when executing command: {e}")


def remove_network_delay_from_pod(namespace, pod_name):
    api = client.CoreV1Api()

    command = ["/bin/sh", "-c", "tc qdisc del dev eth0 root"]

    try:
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
        logger.info(f"Removed network delay from pod {pod_name}: {resp}")
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
        # settings = {
        # TODO loop through kvps
        # }
        dict_set(values, "waku.nodes.volumes", [{"name": "address-data", "emptyDir": {}}], sep=".")
        dict_set(
            values,
            "waku.nodes.volumesMounts",
            [{"name": "address-data", "mountPath": "/etc/addrs"}],
            sep=".",
        )
        dict_set(
            values,
            "waku.nodes.initContainers",
            [JsWakuSettings.client_init_container()],
            sep=".",
        )
        # dict_set(
        #     values,
        #     "waku.nodes.readinessProbe.command",
        #     JsWakuSettings.client_readiness_probe_command(),
        #     sep=".",
        #     replace_leaf=True,
        # )
        dict_set(
            values,
            "waku.nodes.readinessProbe.type",
            "jswaku",
            sep=".",
            replace_leaf=True,
        )
        print(f"values: ```{values}```")
        dict_set(
            values,
            "waku.nodes.command.full.container",
            JsWakuSettings.client_command(sharding),
            sep=".",
        )

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
                '--service-name="zerotesting-lightpush-server.zerotesting"',
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

    deployment_dir: str = Field(default=Path(os.path.dirname(__file__)).parent.parent)
    # extra_paths: List[Path] = [
    #     Path(os.path.dirname(__file__)) / f"bootstrap.values.yaml",
    # ]

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
        def deploy(
            service,
            values,
            *,
            wait_for_ready=False,
            extra_values_paths: Optional[List[Path]] = None,
        ):
            return self.deploy(
                api_client,
                stack,
                args,
                values,
                workdir=workdir,
                service=service,
                wait_for_ready=wait_for_ready,
                extra_values_paths=extra_values_paths,
            )

        self.log_event("run_start")
        sharding = values_yaml.get("sharding_type", "static")
        if sharding != "static":
            raise NotImplementedError(
                "Auto sharding not implemented. It should work on the jswaku side, "
                "but the Lightpush server nodes do not establish connectivity."
            )

        deploy(
            "waku/bootstrap",
            values_yaml,
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
        self.deploy(api_client, stack, args, lps_values, deployment_yaml=lps_deploy)

        lpc_values = deepcopy(values_yaml)
        JsWakuSettings.set_client_values(lpc_values, sharding)

        lpc_deploy = self.build(
            lpc_values,
            Path(workdir) / "client",
            "waku/nodes",
            extra_values_paths=[Path(__file__).parent / "lpc.values.yaml"],
        )
        self.deploy(api_client, stack, args, lpc_values, deployment_yaml=lpc_deploy)


        num_nodes = lpc_deploy["spec"]["replicas"]

        publisher = self.deploy(
            api_client,
            stack,
            args,
            values_yaml,
            service="waku/publisher",
            workdir=workdir,
            extra_values_paths=[Path(__file__).parent / "publisher.values.yaml"],
            wait_for_ready=True,
        )

        namespace = lpc_deploy["metadata"]["namespace"]
        pod_name = "client-0-0"
        delay_ms = 5000
        add_network_delay_to_pod(namespace, pod_name, delay_ms)
        time.sleep(2)
        remove_network_delay_from_pod(namespace, pod_name)

        messages = get_flag_value("messages", publisher["spec"]["containers"][0]["command"])
        delay_seconds = get_flag_value(
            "delay-seconds", publisher["spec"]["containers"][0]["command"]
        )
        timeout = (num_nodes + 5) * messages * delay_seconds * 120
        logger.info(f"Waiting for Ready=False. Timeout: {timeout}")

        if not args.dry_run:
            wait_for_rollout(
                publisher["kind"],
                publisher["metadata"]["name"],
                publisher["metadata"]["namespace"],
                20,
                api_client,
                ("Ready", "False"),
                # TODO [extend condition checks] lambda cond : cond.type == "Ready" and cond.status == "True"
            )

        self.log_event("publisher_messages_finished")
        time.sleep(20)
        self.log_event("publisher_wait_finished")

        self.log_event("internal_run_finished")
        self._metadata_event(self.events_log_path)